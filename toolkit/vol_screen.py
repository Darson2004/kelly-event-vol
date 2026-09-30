#!/usr/bin/env python
"""vol_screen.py -- Volatility Vibes-style earnings-vol screen + move history.

Implements the screening metrics from the Volatility Vibes video
"This Option Strategy Turned $10k Into $1 Million In One Year"
(https://www.youtube.com/watch?v=oW6MHjzxHpU): sell earnings implied vol
only where it is rich versus realized and the term structure is inverted.

Criteria (same thresholds popularized by the video / Acelogic's calculator):
  1. avg 30d share volume >= 1,500,000          (options liquid enough)
  2. IV30 / RV30 >= 1.25                        (implied rich vs Yang-Zhang realized)
  3. term-structure slope (front..45d) <= -0.00406 per day (event inversion)

Commands
--------
screen  Compute the metrics for a ticker from live yfinance data and print a
        Recommended / Consider / Avoid label, plus the exact kelly.py command
        to size the trade.
moves   Export the ticker's historical post-earnings moves to CSV -- this is
        the empirical move distribution kelly.py uses to size the straddle.

Run with:
  python vol_screen.py screen --ticker NVDA
  python vol_screen.py moves --ticker NVDA --out nvda_moves.csv
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

TRADING_DAYS = 252.0


# ---------------------------------------------------------------------------
# Yang-Zhang realized volatility
# ---------------------------------------------------------------------------

def yang_zhang_vol(ohlc: pd.DataFrame, window: int = 30) -> pd.Series:
    """Annualized Yang-Zhang volatility over a rolling window of daily bars.

    Uses overnight (close->open), open->close, and Rogers-Satchell terms:
      sigma_YZ^2 = sigma_o^2 + k * sigma_c^2 + (1-k) * sigma_rs^2
      k = 0.34 / (1.34 + (n+1)/(n-1))
    """
    o = np.log(ohlc["Open"] / ohlc["Close"].shift(1))
    c = np.log(ohlc["Close"] / ohlc["Open"])
    rs = (np.log(ohlc["High"] / ohlc["Close"]) * np.log(ohlc["High"] / ohlc["Open"])
          + np.log(ohlc["Low"] / ohlc["Close"]) * np.log(ohlc["Low"] / ohlc["Open"]))
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    var_o = o.rolling(window).var()
    var_c = c.rolling(window).var()
    var_rs = rs.rolling(window).mean()
    return np.sqrt((var_o + k * var_c + (1 - k) * var_rs) * TRADING_DAYS)


# ---------------------------------------------------------------------------
# ATM IV term structure from yfinance option chains
# ---------------------------------------------------------------------------

def _mid(row) -> float:
    bid, ask = float(row["bid"]), float(row["ask"])
    if bid > 0 and ask > 0:
        return 0.5 * (bid + ask)
    return float(row["lastPrice"])


def implied_vol(price: float, S: float, K: float, T: float, r: float, cp: str) -> float:
    """Invert Black-Scholes by bisection (Yahoo's IV column is unreliable)."""
    from kelly import bs_price
    if price <= max(0.0, (S - K) if cp == "c" else (K - S)) or T <= 0:
        return float("nan")
    lo, hi = 0.005, 5.0
    for _ in range(80):
        m = 0.5 * (lo + hi)
        if bs_price(S, K, T, r, m, cp) < price:
            lo = m
        else:
            hi = m
    return 0.5 * (lo + hi)


def atm_iv_curve(tkr, spot: float, max_dte: int = 120, max_expiries: int = 8, r: float = 0.04):
    """(dte, atm_iv) points: IV backed out from ATM call+put mid prices."""
    points = []
    today = datetime.now(timezone.utc).date()
    for exp in tkr.options[: max_expiries + 4]:
        dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
        if dte < 1 or dte > max_dte:
            continue
        try:
            chain = tkr.option_chain(exp)
        except Exception as e:
            print("  (skipping %s: %s)" % (exp, e))
            continue
        T = dte / 365.0
        ivs = []
        for side, cp in ((chain.calls, "c"), (chain.puts, "p")):
            if side.empty:
                continue
            row = side.iloc[(side["strike"] - spot).abs().argsort().iloc[0]]
            iv = implied_vol(_mid(row), spot, float(row["strike"]), T, r, cp)
            if not math.isnan(iv) and 0.01 < iv < 4.0:
                ivs.append(iv)
        if ivs:
            points.append((dte, float(np.mean(ivs))))
        if len(points) >= max_expiries:
            break
    return sorted(points)


def interp_iv(points, dte: float) -> float:
    """Linear interpolation on the (dte, iv) curve, clamped at the ends."""
    ds = np.array([p[0] for p in points], float)
    vs = np.array([p[1] for p in points], float)
    return float(np.interp(dte, ds, vs))


def atm_straddle_mid(tkr, expiry: str, spot: float):
    """ATM straddle mid price for an expiry (entry premium for kelly.py)."""
    chain = tkr.option_chain(expiry)
    out = 0.0
    for side in (chain.calls, chain.puts):
        row = side.iloc[(side["strike"] - spot).abs().argsort().iloc[0]]
        bid, ask = float(row["bid"]), float(row["ask"])
        mid = 0.5 * (bid + ask) if (bid > 0 and ask > 0) else float(row["lastPrice"])
        out += mid
    return out, float(row["strike"])


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_screen(args):
    import yfinance as yf
    tkr = yf.Ticker(args.ticker)
    hist = tkr.history(period="6mo", auto_adjust=True)
    if hist.empty:
        raise SystemExit("no price history for %s" % args.ticker)
    spot = float(hist["Close"].iloc[-1])

    avg_vol = float(hist["Volume"].rolling(30).mean().iloc[-1])
    rv30 = float(yang_zhang_vol(hist, 30).iloc[-1])

    points = atm_iv_curve(tkr, spot)
    if len(points) < 2:
        raise SystemExit("not enough option expiries with usable IV for %s" % args.ticker)
    iv30 = interp_iv(points, 30)
    front_dte, front_iv = points[0]
    slope = (interp_iv(points, 45) - front_iv) / (45 - front_dte) if front_dte < 45 else 0.0
    iv_rv = iv30 / rv30 if rv30 > 0 else float("nan")

    front_exp = None
    for exp in tkr.options:
        d = (datetime.strptime(exp, "%Y-%m-%d").date()
             - datetime.now(timezone.utc).date()).days
        if d == front_dte:
            front_exp = exp
            break
    straddle_px, strike = (atm_straddle_mid(tkr, front_exp, spot)
                           if front_exp else (float("nan"), float("nan")))

    pass_vol = avg_vol >= args.min_volume
    pass_ivrv = iv_rv >= args.iv_rv
    pass_slope = slope <= args.slope
    if pass_vol and pass_ivrv and pass_slope:
        label = "RECOMMENDED"
    elif pass_slope and (pass_vol or pass_ivrv):
        label = "CONSIDER"
    else:
        label = "AVOID"

    def mark(ok):
        return "PASS" if ok else "fail"

    print("=" * 64)
    print("%s  --  earnings-vol screen (Volatility Vibes criteria)" % args.ticker.upper())
    print("=" * 64)
    print("Spot %.2f | front expiry %s (%d DTE)" % (spot, front_exp, front_dte))
    print("avg 30d volume : %12s  (>= %s)          %s"
          % (format(int(avg_vol), ","), format(int(args.min_volume), ","), mark(pass_vol)))
    print("IV30 / RV30    : %.2f / %.2f = %.2f  (>= %.2f)   %s"
          % (iv30, rv30, iv_rv, args.iv_rv, mark(pass_ivrv)))
    print("term slope     : %+.5f /day (front->45d, <= %.5f) %s"
          % (slope, args.slope, mark(pass_slope)))
    print("IV curve       : %s" % "  ".join("%dd:%.0f%%" % (d, 100 * v) for d, v in points))
    if not math.isnan(straddle_px):
        print("ATM straddle   : %.2f/share at K=%.0f -> implied move +/-%.1f%%"
              % (straddle_px, strike, 100 * straddle_px / spot))
    print("-" * 64)
    print("VERDICT: %s" % label)
    if label != "AVOID" and not math.isnan(straddle_px):
        print()
        print("Next: export the move history, then Kelly-size the short straddle:")
        print("  python vol_screen.py moves --ticker %s --out %s_moves.csv"
              % (args.ticker, args.ticker.lower()))
        print("  python kelly.py straddle --side short --hold event \\")
        print("      --spot %.2f --strike %.0f --dte %d --iv %.2f --iv-exit %.2f \\"
              % (spot, strike, front_dte, front_iv, rv30))
        print("      --entry-price %.2f --moves-file %s_moves.csv --bankroll <equity>"
              % (straddle_px, args.ticker.lower()))
        print("(--iv-exit defaults here to RV30; back-month IV is another good anchor)")


def cmd_moves(args):
    import yfinance as yf
    tkr = yf.Ticker(args.ticker)
    try:
        edates = tkr.get_earnings_dates(limit=args.limit + 8)
    except Exception as e:
        raise SystemExit("could not fetch earnings dates: %s" % e)
    if edates is None or edates.empty:
        raise SystemExit("no earnings dates for %s" % args.ticker)

    hist = tkr.history(period="5y", auto_adjust=True)
    if hist.empty:
        raise SystemExit("no price history returned for %s (rate-limited? retry)" % args.ticker)
    closes = hist["Close"]
    dates = list(closes.index.date)

    now = datetime.now(timezone.utc)
    rows = []
    for ts in edates.index:
        if ts.to_pydatetime().astimezone(timezone.utc) >= now:
            continue
        # announcement after the close -> move shows up the NEXT trading day
        after_close = ts.hour >= 15
        ann_date = ts.date()
        idx = np.searchsorted(dates, ann_date)
        if after_close:
            i_before, i_after = idx, idx + 1
            if idx < len(dates) and dates[idx] != ann_date:
                i_before, i_after = idx - 1, idx
        else:
            i_before, i_after = idx - 1, idx
        if i_before < 0 or i_after >= len(dates):
            continue
        move = float(closes.iloc[i_after] / closes.iloc[i_before] - 1.0)
        rows.append({"date": str(ann_date), "move": round(move, 5)})
        if len(rows) >= args.limit:
            break

    if not rows:
        raise SystemExit("no usable past earnings moves for %s" % args.ticker)
    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    m = df["move"].values
    print("%s: %d past earnings moves -> %s" % (args.ticker.upper(), len(m), args.out))
    print("  mean |move| %.2f%% | median |move| %.2f%% | std %.2f%% | worst %+.2f%% | best %+.2f%%"
          % (100 * np.mean(np.abs(m)), 100 * np.median(np.abs(m)),
             100 * np.std(m), 100 * np.min(m), 100 * np.max(m)))
    print("  parametric fallback for kelly.py: --move-sigma %.3f --t-df 4" % float(np.std(m)))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("screen", help="Volatility Vibes earnings-vol screen")
    s.add_argument("--ticker", required=True)
    s.add_argument("--min-volume", type=float, default=1_500_000)
    s.add_argument("--iv-rv", type=float, default=1.25)
    s.add_argument("--slope", type=float, default=-0.00406)
    s.set_defaults(func=cmd_screen)

    m = sub.add_parser("moves", help="export historical post-earnings moves to CSV")
    m.add_argument("--ticker", required=True)
    m.add_argument("--limit", type=int, default=16, help="max past events (default 16)")
    m.add_argument("--out", default=None)
    m.set_defaults(func=cmd_moves)

    args = p.parse_args(argv)
    if args.cmd == "moves" and not args.out:
        args.out = "%s_moves.csv" % args.ticker.lower()
    args.func(args)


if __name__ == "__main__":
    main()
