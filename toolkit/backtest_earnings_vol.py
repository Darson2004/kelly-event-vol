#!/usr/bin/env python
"""backtest_earnings_vol.py -- structural re-derivation of the Volatility Vibes
earnings IV-crush backtest, using only free (equity) data.

The claim under test (from the video + community summaries):
  sell the ATM front straddle right before earnings, buy it back right after,
  filter for rich/inverted IV, size at <=6%/trade -> ~66% win rate, ~90% CAGR,
  ~20% drawdowns ($10k->$1M was the illustrative full-Kelly line).

What we cannot replicate with free data: the actual historical straddle price
before each event (needs historical option chains: ORATS / Databento OPRA).

What we CAN do: everything else is reconstructable from equity OHLCV --
realized earnings moves, trailing expected-move estimates, ambient vol for the
post-event repricing, real calendar/expiry mechanics. The single unknown, how
richly the market priced each event, is ONE scalar:

    k = implied_move / E_prior[|move|]     (the event VRP multiple)

so we sweep k and ask two questions:
  1. what k does his ~66% win rate require?
  2. at that k, do 6%-sized returns look like ~90% CAGR / 2x-digit DDs,
     or are his numbers internally inconsistent?

Leakage rules: expected |move| per event uses ONLY strictly-prior events
(expanding median, min 4 priors); RV30 uses only data before entry.

Model per event (short straddle; --calendar adds a long 30d back straddle):
  entry:  S = close before announcement; premium = k * E_prior[|move|] * S
          (entry IV backed out of that premium via BS at the true front DTE)
  exit:   next close after announcement; S' = S*(1+move); straddle repriced
          at ambient IV (= trailing RV30) with the true remaining DTE to the
          first Friday expiry (Thu AMC reporters -> ~0 DTE left -> full crush)
  costs:  --cost fraction of premium lost round-trip to spreads (default 0.08)

Usage:
  python backtest_earnings_vol.py run [--tickers AAPL,MSFT,...] [--f 0.06]
      [--cost 0.08] [--k 0.9,1.0,1.05,1.1,1.15,1.2,1.3] [--calendar]
Event data is cached in _bt_cache/ so reruns are instant.
"""

from __future__ import annotations

import argparse
import math
import os
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

from kelly import straddle_value
from vol_screen import yang_zhang_vol

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bt_cache")

# Liquid, regularly-reporting names with active options; mix of megacap,
# high-vol tech and consumer so results aren't one sector's story.
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL", "TSLA", "AMD", "AVGO",
    "QCOM", "MU", "INTC", "CRM", "ORCL", "ADBE", "NFLX", "DIS", "COST",
    "WMT", "TGT", "HD", "NKE", "SBUX", "JPM", "GS", "XOM", "CAT", "BA",
    "UNH", "LLY", "CRWD", "PANW", "DDOG", "SNOW", "PLTR", "SHOP", "PYPL",
    "UBER", "ABNB", "COIN", "SMCI", "CAVA",
]


# ---------------------------------------------------------------------------
# Event collection (cached per ticker)
# ---------------------------------------------------------------------------

def fetch_ticker_events(ticker: str, retries: int = 3) -> pd.DataFrame | None:
    """Past earnings events with realized move, trailing RV30, spot at entry."""
    cache = os.path.join(CACHE_DIR, "%s_events.csv" % ticker)
    if os.path.exists(cache):
        return pd.read_csv(cache, parse_dates=["ann_date", "entry_date", "exit_date"])

    import yfinance as yf
    for attempt in range(retries):
        try:
            tkr = yf.Ticker(ticker)
            edates = tkr.get_earnings_dates(limit=40)
            hist = tkr.history(period="6y", auto_adjust=True)
            if edates is None or edates.empty or hist.empty:
                raise RuntimeError("empty data")
            break
        except Exception as e:
            if attempt == retries - 1:
                print("  %s: FAILED (%s)" % (ticker, e))
                return None
            time.sleep(8 * (attempt + 1))

    rv = yang_zhang_vol(hist, 30)
    closes = hist["Close"]
    vol_avg = hist["Volume"].rolling(30).mean()
    dates = list(closes.index.date)
    now = pd.Timestamp.now(tz="UTC")

    rows = []
    for ts in edates.index:
        if ts.tz_convert("UTC") >= now - pd.Timedelta(days=2):
            continue
        after_close = ts.hour >= 15
        ann = ts.date()
        idx = int(np.searchsorted(dates, ann))
        if after_close:
            i_before, i_after = idx, idx + 1
            if idx < len(dates) and dates[idx] != ann:
                i_before, i_after = idx - 1, idx
        else:
            i_before, i_after = idx - 1, idx
        if i_before < 1 or i_after >= len(dates):
            continue
        entry_d, exit_d = dates[i_before], dates[i_after]
        s0 = float(closes.iloc[i_before])
        move = float(closes.iloc[i_after] / s0 - 1.0)
        rv30 = float(rv.iloc[i_before]) if not math.isnan(rv.iloc[i_before]) else None
        av = float(vol_avg.iloc[i_before]) if not math.isnan(vol_avg.iloc[i_before]) else 0.0
        if rv30 is None or s0 < 5.0:
            continue
        rows.append({"ticker": ticker, "ann_date": ann, "entry_date": entry_d,
                     "exit_date": exit_d, "spot": s0, "move": move,
                     "rv30": rv30, "avg_volume": av})
    if not rows:
        return None
    df = pd.DataFrame(rows).sort_values("ann_date").reset_index(drop=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def build_events(tickers) -> pd.DataFrame:
    frames = []
    for i, t in enumerate(tickers):
        df = fetch_ticker_events(t)
        if df is not None and len(df) >= 6:
            frames.append(df)
            print("  %-6s %2d events" % (t, len(df)))
        time.sleep(1.0)
    ev = pd.concat(frames, ignore_index=True)
    for c in ("ann_date", "entry_date", "exit_date"):
        ev[c] = pd.to_datetime(ev[c])

    # leakage-free expected |move|: expanding median of strictly-prior events
    ev = ev.sort_values(["ticker", "ann_date"]).reset_index(drop=True)
    exp_moves = []
    for t, grp in ev.groupby("ticker"):
        prior = grp["move"].abs().expanding().mean().shift(1)
        n_prior = np.arange(len(grp))
        exp_moves.append(pd.DataFrame({"idx": grp.index,
                                       "exp_move": prior.values,
                                       "n_prior": n_prior}))
    em = pd.concat(exp_moves).set_index("idx")
    ev["exp_move"] = em["exp_move"]
    ev["n_prior"] = em["n_prior"]
    ev = ev[(ev["n_prior"] >= 4) & ev["exp_move"].notna()].copy()
    return ev.sort_values("ann_date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Trade model
# ---------------------------------------------------------------------------

def next_friday(d: date) -> date:
    return d + timedelta(days=(4 - d.weekday()) % 7)


def implied_vol_from_price(price, S, K, T, r=0.0, lo=0.01, hi=8.0):
    for _ in range(60):
        m = 0.5 * (lo + hi)
        if straddle_value(S, K, T, r, m) < price:
            lo = m
        else:
            hi = m
    return 0.5 * (lo + hi)


def simulate_event(row, k: float, calendar: bool, back_crush: float):
    """Gross return per $1 of front premium for one event at VRP multiple k."""
    S = row.spot
    entry_d = row.entry_date.date() if hasattr(row.entry_date, "date") else row.entry_date
    exit_d = row.exit_date.date() if hasattr(row.exit_date, "date") else row.exit_date
    expiry = next_friday(exit_d)
    dte_front = max((expiry - entry_d).days, 1)
    T_front = dte_front / 365.0
    T_rem = (expiry - exit_d).days / 365.0

    # entry straddle = one event day of k-scaled move variance + (dte-1)
    # ordinary days at ambient vol (real pre-earnings straddles price both)
    ev_prem = k * row.exp_move * S
    if ev_prem <= 0.003 * S:
        return None
    iv_event = implied_vol_from_price(ev_prem, S, S, 1.0 / 365.0)
    var_total = iv_event ** 2 * (1.0 / 365.0) + row.rv30 ** 2 * ((dte_front - 1) / 365.0)
    iv_entry = math.sqrt(var_total / T_front)
    premium = straddle_value(S, S, T_front, 0.0, iv_entry)
    S_after = S * (1.0 + row.move)
    iv_post = row.rv30
    exit_front = straddle_value(S_after, S, T_rem, 0.0, iv_post)
    r_short = (premium - exit_front) / premium

    if not calendar:
        return r_short

    # ATM calendar: short the front straddle, long the 30d back straddle.
    # The back leg also carries the event variance (the event sits inside its
    # window), diluted over 30 days; post-event every IV reverts to ambient.
    # Return is per $1 of DEBIT (the capital his 6%-of-port sizing refers to).
    T_back = 30.0 / 365.0
    T_back_rem = T_back - (exit_d - entry_d).days / 365.0
    iv_back = math.sqrt((iv_event ** 2 * (1.0 / 365.0)
                         + row.rv30 ** 2 * (29.0 / 365.0)) / T_back)
    back_entry = straddle_value(S, S, T_back, 0.0, iv_back)
    back_exit = straddle_value(S_after, S, T_back_rem, 0.0,
                               max(row.rv30 - back_crush, 0.05))
    debit = back_entry - premium
    if debit <= 0.003 * S:
        return None
    return ((back_exit - exit_front) - debit) / debit


# ---------------------------------------------------------------------------
# Portfolio simulation & metrics
# ---------------------------------------------------------------------------

def run_backtest(ev: pd.DataFrame, k: float, f: float, cost: float,
                 calendar: bool, back_crush: float, day_cap: float = 0.30):
    trades = []
    for row in ev.itertuples():
        r = simulate_event(row, k, calendar, back_crush)
        if r is None:
            continue
        trades.append({"date": row.ann_date, "ticker": row.ticker,
                       "r_net": r - cost})
    tr = pd.DataFrame(trades).sort_values("date").reset_index(drop=True)

    equity, curve = 1.0, []
    for d, day in tr.groupby("date"):
        f_each = min(f, day_cap / len(day))
        pnl = float(np.sum(f_each * day["r_net"].values))
        equity *= max(1.0 + pnl, 1e-6)
        curve.append((d, equity))
    curve = pd.DataFrame(curve, columns=["date", "equity"]).set_index("date")

    span_years = (tr["date"].iloc[-1] - tr["date"].iloc[0]).days / 365.25
    n = len(tr)
    cagr = curve["equity"].iloc[-1] ** (1 / span_years) - 1 if span_years > 0 else np.nan
    eq_ret = curve["equity"].pct_change().dropna()
    events_per_year = len(curve) / span_years
    sharpe = (eq_ret.mean() / eq_ret.std() * math.sqrt(events_per_year)
              if eq_ret.std() > 0 else np.nan)
    peak = curve["equity"].cummax()
    max_dd = float((curve["equity"] / peak - 1.0).min())
    return {
        "k": k, "n_trades": n, "win_rate": float((tr["r_net"] > 0).mean()),
        "avg_r": float(tr["r_net"].mean()), "med_r": float(tr["r_net"].median()),
        "worst_r": float(tr["r_net"].min()), "cagr": cagr, "sharpe": sharpe,
        "max_dd": max_dd, "trades_yr": n / span_years,
    }


def cmd_run(args):
    tickers = args.tickers.split(",") if args.tickers else DEFAULT_UNIVERSE
    print("Building event universe (%d tickers, cached in _bt_cache/)..." % len(tickers))
    ev = build_events(tickers)
    print("\n%d usable events, %s..%s, %d tickers\n"
          % (len(ev), ev["ann_date"].min().date(), ev["ann_date"].max().date(),
             ev["ticker"].nunique()))

    ks = [float(x) for x in args.k.split(",")]
    mode = "ATM CALENDAR" if args.calendar else "SHORT ATM STRADDLE"
    print("Strategy: %s through earnings | f=%.0f%%/trade | cost=%.0f%% of premium"
          % (mode, 100 * args.f, 100 * args.cost))
    print("(k = implied move / trailing MEAN |move| -- the event VRP multiple)\n")
    hdr = "%5s %8s %9s %8s %8s %8s %8s %9s %9s" % (
        "k", "trades", "win rate", "avg R", "med R", "worst R", "CAGR", "Sharpe", "max DD")
    print(hdr)
    print("-" * len(hdr))
    for k in ks:
        m = run_backtest(ev, k, args.f, args.cost, args.calendar, args.back_crush)
        print("%5.2f %8d %8.1f%% %+7.3f %+7.3f %+7.2f %7.1f%% %9.2f %8.1f%%"
              % (m["k"], m["n_trades"], 100 * m["win_rate"], m["avg_r"], m["med_r"],
                 m["worst_r"], 100 * m["cagr"], m["sharpe"], 100 * m["max_dd"]))
    print()
    print("Read: find the k row matching his ~66%% win rate, then check whether")
    print("CAGR/Sharpe/DD at that k are anywhere near the claimed ~90%%/high/~20%%.")
    print("Lit. anchor: implied earnings moves have averaged ~1.0-1.15x the mean")
    print("realized |move| depending on era (and BELOW 1.0 in 2025-2026 seasons).")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the k-sweep backtest")
    r.add_argument("--tickers", default=None, help="comma list (default: built-in 42)")
    r.add_argument("--f", type=float, default=0.06, help="fraction per trade (default 6%%)")
    r.add_argument("--cost", type=float, default=0.08,
                   help="round-trip cost as fraction of premium (default 8%%)")
    r.add_argument("--k", default="0.90,1.00,1.05,1.10,1.15,1.20,1.30")
    r.add_argument("--calendar", action="store_true",
                   help="ATM calendar (long 30d back straddle) instead of naked short")
    r.add_argument("--back-crush", type=float, default=0.0,
                   help="extra abs IV points the back leg bleeds post-event (default 0)")
    r.set_defaults(func=cmd_run)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
