#!/usr/bin/env python
"""event_vol.py -- pre-earnings event-vol extraction + buy-side screen.

Buy-side mirror of vol_screen.py, implementing the Volatility Vibes
"Earnings Volatility Strategy" (youtube.com/watch?v=0YfQpYhMNH0): buy the
ATM straddle ~14 days before earnings when the IMPLIED EARNINGS MOVE is
cheap versus the name's own history, exit just before the announcement.

Math (verified in scripts/verify_vv_math.py):
  total_var(T) = event_var * 1d + ambient_var * (T-1)d      (additivity)
  implied_move = sqrt(event_var_daily) * sqrt(2/pi)
  With ambient fairly priced and no event repricing, the T-14 -> T-0 long
  straddle is zero-EV before costs; the edge is event repricing + ambient
  (RV - IV) - costs.

Commands
--------
screen    Extract event vol / implied move for one ticker from live chains,
          compare vs its realized-move history, print verdict + structures.
snapshot  Run extraction for a list of tickers and append one row each to
          implied_move_history.csv -- accumulates the implied-move history
          (vs-past-implied signals) that cannot be backfilled from free data.

Run with:
  python event_vol.py screen --ticker NVDA
  python event_vol.py snapshot --tickers NVDA,WMT,HD
"""

from __future__ import annotations

import argparse
import csv
import math
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from vol_screen import yang_zhang_vol, implied_vol, _mid, atm_straddle_mid

C_ABS = math.sqrt(2.0 / math.pi)   # E|X| = C_ABS * sigma for X ~ N(0, sigma^2)
DAYS = 365.0
HIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "implied_move_history.csv")


# ---------------------------------------------------------------------------
# earnings date
# ---------------------------------------------------------------------------

def next_earnings(tkr):
    """(date, 'AMC'|'BMO') of the next earnings event, or (None, None)."""
    now = datetime.now(timezone.utc)
    try:
        ed = tkr.get_earnings_dates(limit=12)
        if ed is not None and not ed.empty:
            fut = [ts for ts in ed.index if ts.to_pydatetime().astimezone(timezone.utc) > now]
            if fut:
                ts = min(fut)
                return ts.date(), ("AMC" if ts.hour >= 15 else "BMO")
    except Exception:
        pass
    try:  # fallback: tkr.calendar
        cal = tkr.calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if dates:
            d = min(x for x in dates if x > now.date())
            return d, "AMC"  # session unknown; AMC is the conservative guess
    except Exception:
        pass
    return None, None


# ---------------------------------------------------------------------------
# ATM IV for one expiry (mid of call+put BS inversions)
# ---------------------------------------------------------------------------

def atm_iv(tkr, expiry: str, spot: float, r: float = 0.04):
    dte = (datetime.strptime(expiry, "%Y-%m-%d").date()
           - datetime.now(timezone.utc).date()).days
    chain = tkr.option_chain(expiry)
    T = max(dte, 0.5) / DAYS
    ivs = []
    for side, cp in ((chain.calls, "c"), (chain.puts, "p")):
        if side.empty:
            continue
        row = side.iloc[(side["strike"] - spot).abs().argsort().iloc[0]]
        iv = implied_vol(_mid(row), spot, float(row["strike"]), T, r, cp)
        if not math.isnan(iv) and 0.01 < iv < 5.0:
            ivs.append(iv)
    return (float(np.mean(ivs)) if ivs else float("nan")), dte


# ---------------------------------------------------------------------------
# event-vol extraction
# ---------------------------------------------------------------------------

def extract_event_vol(tkr, spot: float, edate, session: str):
    """Back out event variance and implied move via variance additivity.

    Returns dict or raises. capture = date whose close completes the event
    return: E for BMO, next trading day (approx E+1) for AMC. An expiry on
    day E with an AMC announcement closes before the release -> still ambient.
    """
    capture = edate if session == "BMO" else edate + timedelta(days=1)
    pre_ok = edate if session == "AMC" else edate - timedelta(days=1)

    expiries = [datetime.strptime(e, "%Y-%m-%d").date() for e in tkr.options]
    pre = [e for e in expiries if e <= pre_ok]
    post = [e for e in expiries if e >= capture]
    if not post:
        raise RuntimeError("no post-earnings expiry listed yet")
    e_post = min(post)
    iv_post, dte_post = atm_iv(tkr, e_post.isoformat(), spot)
    if math.isnan(iv_post) or dte_post < 1:
        raise RuntimeError("could not invert IV for post-event expiry %s" % e_post)

    # ambient: pre-event expiry if one exists, else forward vol between the
    # first two post-event expiries (event component cancels).
    if pre:
        e_amb = max(pre)
        iv_amb, dte_amb = atm_iv(tkr, e_amb.isoformat(), spot)
        amb_src = "pre-event expiry %s (%dd)" % (e_amb, dte_amb)
    elif len(post) >= 2:
        e2 = sorted(post)[1]
        iv2, dte2 = atm_iv(tkr, e2.isoformat(), spot)
        fwd_var = (iv2**2 * dte2 - iv_post**2 * dte_post) / max(dte2 - dte_post, 1)
        iv_amb = math.sqrt(max(fwd_var, 1e-4))
        amb_src = "forward vol %s->%s" % (e_post, e2)
    else:
        raise RuntimeError("no way to estimate ambient vol")
    if math.isnan(iv_amb):
        raise RuntimeError("could not invert ambient IV")

    # additivity in absolute variance units (calendar-day convention, as VV)
    var_total = iv_post**2 * dte_post / DAYS
    var_amb = iv_amb**2 * max(dte_post - 1, 0) / DAYS
    var_event = var_total - var_amb
    move = C_ABS * math.sqrt(var_event) if var_event > 0 else float("nan")

    return {"expiry_post": e_post.isoformat(), "dte_post": dte_post,
            "iv_post": iv_post, "iv_amb": iv_amb, "amb_src": amb_src,
            "var_event": var_event, "implied_move": move}


def realized_moves(tkr, limit: int = 12):
    """|post-earnings close-to-close moves| via vol_screen's session logic."""
    ed = tkr.get_earnings_dates(limit=limit + 8)
    hist = tkr.history(period="5y", auto_adjust=True)
    closes = hist["Close"]
    dates = list(closes.index.date)
    now = datetime.now(timezone.utc)
    out = []
    for ts in ed.index:
        if ts.to_pydatetime().astimezone(timezone.utc) >= now:
            continue
        after_close = ts.hour >= 15
        ann = ts.date()
        idx = np.searchsorted(dates, ann)
        if after_close:
            i0, i1 = idx, idx + 1
            if idx < len(dates) and dates[idx] != ann:
                i0, i1 = idx - 1, idx
        else:
            i0, i1 = idx - 1, idx
        if i0 < 0 or i1 >= len(dates):
            continue
        out.append(abs(float(closes.iloc[i1] / closes.iloc[i0] - 1.0)))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# screen
# ---------------------------------------------------------------------------

def run_extraction(ticker: str, earnings: str | None, session_flag: str | None):
    import yfinance as yf
    tkr = yf.Ticker(ticker)
    hist = tkr.history(period="6mo", auto_adjust=True)
    if hist.empty:
        raise SystemExit("no price history for %s" % ticker)
    spot = float(hist["Close"].iloc[-1])
    rv30 = float(yang_zhang_vol(hist, 30).iloc[-1])

    if earnings:
        edate = datetime.strptime(earnings, "%Y-%m-%d").date()
        session = session_flag or "AMC"
    else:
        edate, session = next_earnings(tkr)
        if session_flag:
            session = session_flag
        if edate is None:
            raise SystemExit("could not determine next earnings date for %s "
                             "(pass --earnings YYYY-MM-DD)" % ticker)
    dte_event = (edate - datetime.now(timezone.utc).date()).days

    ev = extract_event_vol(tkr, spot, edate, session)
    moves = realized_moves(tkr)
    return tkr, spot, rv30, edate, session, dte_event, ev, moves


def cmd_screen(args):
    tkr, spot, rv30, edate, session, dte_event, ev, moves = run_extraction(
        args.ticker, args.earnings, args.session)

    mean_r = float(np.mean(moves)) if moves else float("nan")
    last_r = moves[0] if moves else float("nan")
    mv = ev["implied_move"]
    r_avg = mv / mean_r if mean_r else float("nan")
    r_last = mv / last_r if last_r else float("nan")
    amb_vs_rv = ev["iv_amb"] / rv30 if rv30 > 0 else float("nan")

    # Placeholder decision rule until a fitted model exists. His backtest
    # direction: lower implied-vs-history => better long-straddle returns.
    if not math.isnan(r_avg) and r_avg <= 0.90 and (math.isnan(r_last) or r_last <= 1.10):
        label = "CHEAP -- long-event-vol candidate"
    elif not math.isnan(r_avg) and r_avg >= 1.15:
        label = "RICH -- belongs to the SELL screen (vol_screen.py), not this one"
    else:
        label = "FAIR -- no edge either way"

    print("=" * 68)
    print("%s  --  pre-earnings event-vol screen (buy side)" % args.ticker.upper())
    print("=" * 68)
    print("Spot %.2f | earnings %s (%s), T-%d | post-event expiry %s (%dd)"
          % (spot, edate, session, dte_event, ev["expiry_post"], ev["dte_post"]))
    print("ambient IV     : %.1f%%  (%s)" % (100 * ev["iv_amb"], ev["amb_src"]))
    print("total IV       : %.1f%%  (post-event expiry ATM)" % (100 * ev["iv_post"]))
    print("implied move   : +/-%.2f%%" % (100 * mv))
    print("realized hist  : mean |move| %.2f%% | last %.2f%% | n=%d"
          % (100 * mean_r, 100 * last_r, len(moves)))
    print("SIGNALS  implied/avg_realized %.2f | implied/last_realized %.2f | ambientIV/RV30 %.2f"
          % (r_avg, r_last, amb_vs_rv))
    print("-" * 68)
    print("VERDICT: %s" % label)

    if label.startswith("CHEAP"):
        st_px, k = atm_straddle_mid(tkr, ev["expiry_post"], spot)
        print()
        print("Structures (enter ~T-14, exit just before the announcement):")
        print("  A. long ATM straddle %s K=%.0f  ~%.2f/share (%.1f%% of spot)"
              % (ev["expiry_post"], k, st_px, 100 * st_px / spot))
        if "pre-event expiry" in ev["amb_src"]:
            e_amb = ev["amb_src"].split()[2]
            try:
                st_amb, k2 = atm_straddle_mid(tkr, e_amb, spot)
                print("  B. event calendar: SELL %s straddle ~%.2f / BUY %s straddle ~%.2f"
                      % (e_amb, st_amb, ev["expiry_post"], st_px))
                print("     net debit ~%.2f -- strips the ~2/3 ambient carry, isolates the event"
                      % (st_px - st_amb))
            except Exception:
                pass
        print("  size: 0.5-1%% of equity in premium per name until the backtest exists;")
        print("  cap at 5%% of the ticker's daily option volume. Exit day-of, before the print.")


def cmd_snapshot(args):
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    today = datetime.now(timezone.utc).date().isoformat()
    exists = os.path.exists(HIST_FILE)
    wrote = 0
    with open(HIST_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["obs_date", "ticker", "earnings_date", "session",
                        "dte_to_event", "spot", "iv_ambient", "iv_total",
                        "dte_post", "implied_move", "mean_realized",
                        "last_realized", "ratio_avg", "ratio_last", "rv30"])
        for t in tickers:
            try:
                _, spot, rv30, edate, session, dte_event, ev, moves = run_extraction(t, None, None)
                mean_r = float(np.mean(moves)) if moves else float("nan")
                last_r = moves[0] if moves else float("nan")
                mv = ev["implied_move"]
                w.writerow([today, t, edate.isoformat(), session, dte_event,
                            round(spot, 2), round(ev["iv_amb"], 4),
                            round(ev["iv_post"], 4), ev["dte_post"],
                            round(mv, 5), round(mean_r, 5), round(last_r, 5),
                            round(mv / mean_r, 3) if mean_r else "",
                            round(mv / last_r, 3) if last_r else "",
                            round(rv30, 4)])
                wrote += 1
                print("%-6s T-%-3d move %.2f%%  vs avg %.2f%% (ratio %.2f)"
                      % (t, dte_event, 100 * mv, 100 * mean_r,
                         mv / mean_r if mean_r else float("nan")))
            except Exception as e:
                print("%-6s SKIP: %s" % (t, e))
    print("appended %d rows -> %s" % (wrote, HIST_FILE))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("screen", help="buy-side event-vol screen for one ticker")
    s.add_argument("--ticker", required=True)
    s.add_argument("--earnings", default=None, help="YYYY-MM-DD override")
    s.add_argument("--session", choices=["BMO", "AMC"], default=None)
    s.set_defaults(func=cmd_screen)

    n = sub.add_parser("snapshot", help="append implied-move rows for tickers")
    n.add_argument("--tickers", required=True, help="comma-separated list")
    n.set_defaults(func=cmd_snapshot)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
