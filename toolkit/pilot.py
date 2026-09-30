#!/usr/bin/env python
"""pilot.py -- pre-earnings long-straddle PILOT console. DECISION SUPPORT ONLY.

This file CANNOT send an order. It has no broker connection, no FIX session
and no order-entry code, by design: the strategy trades ~32 times a year and
is latency-insensitive, so automating execution would add a large failure
surface (legging risk, runaway orders) for no measurable gain. Orders go
through the broker's native multi-leg complex-order ticket, by hand.

Commands
--------
calendar            what is coming up across the 42-name universe, and which
                    events hit their T-14 entry inside the next N days
screen --ticker X   full GO / NO-GO card for one name, every gate shown
due [--days N]      screen every name whose T-14 entry lands within N days
log ...             append one fill record (this is the pilot evidence)
report              realised phi and slippage from the log, vs the backtest

Run:
  python pilot.py due
"""

from __future__ import annotations

import argparse
import csv
import math
import os
from datetime import datetime, timedelta, timezone

import numpy as np

from event_vol import (C_ABS, extract_event_vol, next_earnings,  # noqa: F401
                       realized_moves)
from vol_screen import atm_straddle_mid, _mid  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "pilot_fills.csv")

# ---------------------------------------------------------------------------
# THE RULES. Every number below traces to a specific piece of evidence.
# ---------------------------------------------------------------------------

# Universe: the 42 liquid names the graduated backtest ran on. Small/mid caps
# are PROVEN untradeable here -- spread was 3x the edge at every cheapness
# depth (2026-08-26 Databento run). Do not add names casually.
UNIVERSE = ["AAPL", "ABNB", "ADBE", "AMD", "AMZN", "AVGO", "BA", "CAT",
            "CAVA", "COIN", "COST", "CRM", "CRWD", "DDOG", "DIS", "GOOGL",
            "GS", "HD", "INTC", "JPM", "LLY", "META", "MSFT", "MU", "NFLX",
            "NKE", "NVDA", "ORCL", "PANW", "PLTR", "PYPL", "QCOM", "SBUX",
            "SHOP", "SMCI", "SNOW", "TGT", "TSLA", "UBER", "UNH", "WMT",
            "XOM"]

RULE_RATIO_MAX = 0.90    # ratio_avg_rm <= 0.90  <- THE graduated entry rule
MIN_PRIORS = 2           # engine.py min_priors; fewer priors = no signal
ENTRY_LEAD = 14          # calendar days before the announcement
ENTRY_WINDOW = 4         # engine.py entry_window: +/- days around T-14

# Execution gates, from the $52.65 OPRA tcbbo study (POLICY v2 / A4).
MIN_TICKS_PREFERRED = 2  # at 1 tick there is NO price strictly inside the
                         # touch, so phi is pinned ~0.65-0.89 by arithmetic
COST_FRAC_WARN = 0.020   # one-way half-spread / mid. 2026 median is ~2.76%,
                         # vs 1.08% in 2023 -- the regime has 2.6x'd
PHI_PLAN = 0.50          # planning phi per crossing at realistic clip size
                         # (measured 0.393 at 1 lot, 0.456 at >=10,
                         #  0.583 at >=25). Band 0.40-0.55.
EDGE_GROSS = 0.0639 + 0.0130   # graduated net +6.39% was already net of an
                               # assumed 130bp round trip; add it back to get
                               # the gross the toll is subtracted from


def tick_size(mid: float) -> float:
    """OPRA grid: $0.01 under $3.00, $0.05 at or above."""
    return 0.01 if mid < 3.0 else 0.05


def straddle_quote(tkr, expiry: str, spot: float):
    """ATM straddle mid, ABSOLUTE quoted spread, and strike, from live quotes.

    vol_screen.atm_straddle_mid returns only the mid, and silently falls back
    to lastPrice when a side is missing -- unusable for an execution gate,
    where the spread IS the measurement. This returns NaN spread rather than
    a fabricated one when either leg has no two-sided market.
    """
    chain = tkr.option_chain(expiry)
    mid_tot, spr_tot, strike = 0.0, 0.0, float("nan")
    for side in (chain.calls, chain.puts):
        row = side.iloc[(side["strike"] - spot).abs().argsort().iloc[0]]
        bid, ask = float(row["bid"]), float(row["ask"])
        strike = float(row["strike"])
        if not (bid > 0 and ask > bid):
            return float("nan"), float("nan"), strike
        mid_tot += 0.5 * (bid + ask)
        spr_tot += ask - bid
    return mid_tot, spr_tot, strike


def _fmt(x, n=3, pct=False):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "  n/a"
    return ("%.*f%%" % (n - 1, 100 * x)) if pct else ("%.*f" % (n, x))


# ---------------------------------------------------------------------------
# the card
# ---------------------------------------------------------------------------

def evaluate(ticker: str, earnings: str | None = None,
             session_flag: str | None = None) -> dict:
    """Everything needed for a GO / NO-GO on one name. Never places an order."""
    import yfinance as yf
    tkr = yf.Ticker(ticker)
    hist = tkr.history(period="6mo", auto_adjust=True)
    if hist.empty:
        return {"ticker": ticker, "error": "no price history"}
    spot = float(hist["Close"].iloc[-1])

    if earnings:
        edate = datetime.strptime(earnings, "%Y-%m-%d").date()
        session = session_flag or "AMC"
    else:
        edate, session = next_earnings(tkr)
        session = session_flag or session or "AMC"
    if edate is None:
        return {"ticker": ticker, "error": "no earnings date"}

    today = datetime.now(timezone.utc).date()
    dte_event = (edate - today).days
    entry_date = edate - timedelta(days=ENTRY_LEAD)
    days_to_entry = (entry_date - today).days

    r = {"ticker": ticker, "spot": spot, "ann_date": edate.isoformat(),
         "session": session, "dte_event": dte_event,
         "entry_date": entry_date.isoformat(), "days_to_entry": days_to_entry,
         "in_universe": ticker in UNIVERSE}

    # --- signal ---------------------------------------------------------
    try:
        ev = extract_event_vol(tkr, spot, edate, session)
    except Exception as exc:                                   # noqa: BLE001
        return {**r, "error": "event-vol extraction failed: %s" % exc}
    r["implied_move"] = im = ev["implied_move"]
    r["expiry_post"] = ev["expiry_post"]
    r["dte_post"] = ev["dte_post"]
    r["iv_post"], r["iv_amb"] = ev["iv_post"], ev["iv_amb"]
    # the straddle we would actually buy: ATM at the first post-event expiry
    mid, spr, k = straddle_quote(tkr, ev["expiry_post"], spot)
    r["straddle_mid"], r["straddle_spread"], r["strike"] = mid, spr, k

    moves = realized_moves(tkr)
    r["n_prior_rm"] = len(moves)
    r["avg_prior_rm"] = float(np.mean(moves)) if moves else float("nan")
    r["last_prior_rm"] = float(moves[0]) if moves else float("nan")
    r["ratio_avg_rm"] = (im / r["avg_prior_rm"]
                         if im and r["avg_prior_rm"] > 0 else float("nan"))

    # --- execution ------------------------------------------------------
    mid, spr = r["straddle_mid"], r["straddle_spread"]
    if mid and mid > 0 and math.isfinite(spr):
        r["cost_frac"] = spr / (2.0 * mid)
        # both legs quote on their own grid, so the straddle spans 2 grids
        r["width_ticks"] = spr / (2.0 * tick_size(mid / 2.0))
        r["prem_frac"] = mid / spot
    else:
        r["cost_frac"] = r["width_ticks"] = r["prem_frac"] = float("nan")

    # --- verdict --------------------------------------------------------
    gates, blockers, warnings = [], [], []

    ok_univ = r["in_universe"]
    gates.append(("universe", ok_univ,
                  "in the 42 liquid names" if ok_univ
                  else "NOT in the tested universe"))
    if not ok_univ:
        blockers.append("outside the tested universe")

    ok_pri = r["n_prior_rm"] >= MIN_PRIORS
    gates.append(("history", ok_pri, "%d prior moves (need %d)"
                  % (r["n_prior_rm"], MIN_PRIORS)))
    if not ok_pri:
        blockers.append("insufficient realized-move history")

    ratio = r["ratio_avg_rm"]
    ok_sig = math.isfinite(ratio) and ratio <= RULE_RATIO_MAX
    gates.append(("SIGNAL ratio_avg_rm <= %.2f" % RULE_RATIO_MAX, ok_sig,
                  "%s (implied %s vs avg realized %s)"
                  % (_fmt(ratio), _fmt(im, pct=True), _fmt(r["avg_prior_rm"], pct=True))))
    if not ok_sig:
        blockers.append("implied move is not cheap vs the name's own history")

    in_win = abs(days_to_entry) <= ENTRY_WINDOW
    gates.append(("timing T-%d (+/-%d)" % (ENTRY_LEAD, ENTRY_WINDOW), in_win,
                  "entry %s, %+d days away" % (r["entry_date"], days_to_entry)))
    if not in_win:
        blockers.append("outside the T-14 entry window")

    w = r["width_ticks"]
    ok_w = math.isfinite(w) and w >= MIN_TICKS_PREFERRED
    gates.append(("execution width >= %d ticks" % MIN_TICKS_PREFERRED, ok_w,
                  "%s ticks quoted" % _fmt(w, 1)))
    if not ok_w:
        warnings.append("1-tick market: no price exists strictly inside the "
                        "touch, so expect phi ~0.65+, not 0.50")

    cf = r["cost_frac"]
    ok_c = math.isfinite(cf) and cf <= COST_FRAC_WARN
    gates.append(("execution cost <= %.1f%%" % (100 * COST_FRAC_WARN), ok_c,
                  "%s one-way half-spread" % _fmt(cf, pct=True)))
    if not ok_c:
        warnings.append("wide vs the 2023-25 norm; the 2026 regime is already "
                        "2.6x more expensive and that eats ~a quarter of the edge")

    toll = 2 * PHI_PLAN * cf if math.isfinite(cf) else float("nan")
    r["round_trip_toll"] = toll
    r["expected_net"] = EDGE_GROSS - toll if math.isfinite(toll) else float("nan")
    r["gates"] = gates
    r["blockers"] = blockers
    r["warnings"] = warnings
    r["verdict"] = ("GO" if not blockers and not warnings else
                    "GO (with caveats)" if not blockers else "NO")
    return r


def print_card(r: dict) -> None:
    if r.get("error"):
        print("  %-6s ERROR %s" % (r["ticker"], r["error"]))
        return
    print("=" * 72)
    print("%-6s  %s %s   spot %.2f   entry %s (%+d d)   VERDICT: %s"
          % (r["ticker"], r["ann_date"], r["session"], r["spot"],
             r["entry_date"], r["days_to_entry"], r["verdict"]))
    print("-" * 72)
    for name, ok, detail in r["gates"]:
        print("  [%s] %-34s %s" % ("PASS" if ok else "FAIL", name, detail))
    if math.isfinite(r.get("round_trip_toll", float("nan"))):
        print("-" * 72)
        print("  straddle mid %s  premium %s of spot  toll %s  expected net %s"
              % (_fmt(r["straddle_mid"], 2), _fmt(r["prem_frac"], pct=True),
                 _fmt(r["round_trip_toll"], pct=True),
                 _fmt(r["expected_net"], pct=True)))
    for b in r["blockers"]:
        print("  BLOCKER: %s" % b)
    for w in r["warnings"]:
        print("  WARNING: %s" % w)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_calendar(args):
    import yfinance as yf
    today = datetime.now(timezone.utc).date()
    rows = []
    for t in UNIVERSE:
        try:
            ed, sess = next_earnings(yf.Ticker(t))
        except Exception:                                       # noqa: BLE001
            ed, sess = None, None
        if ed is None:
            continue
        entry = ed - timedelta(days=ENTRY_LEAD)
        rows.append((entry, ed, t, sess, (entry - today).days))
    rows.sort()
    print("T-%d entry calendar, %d names, as of %s" % (ENTRY_LEAD, len(rows), today))
    print("%-12s %-12s %-6s %-5s %s" % ("ENTRY", "ANNOUNCE", "TKR", "SESS", "days to entry"))
    for entry, ed, t, sess, d in rows:
        flag = "  <-- ACTIONABLE" if abs(d) <= ENTRY_WINDOW else ""
        print("%-12s %-12s %-6s %-5s %+5d%s"
              % (entry, ed, t, sess or "?", d, flag))


def cmd_screen(args):
    print_card(evaluate(args.ticker, args.earnings, args.session))


def cmd_due(args):
    import yfinance as yf
    today = datetime.now(timezone.utc).date()
    due = []
    for t in UNIVERSE:
        try:
            ed, _ = next_earnings(yf.Ticker(t))
        except Exception:                                       # noqa: BLE001
            continue
        if ed is None:
            continue
        d = ((ed - timedelta(days=ENTRY_LEAD)) - today).days
        if -ENTRY_WINDOW <= d <= args.days:
            due.append((d, t))
    due.sort()
    if not due:
        print("nothing hits its T-%d entry within %d days." % (ENTRY_LEAD, args.days))
        return
    print("%d name(s) approaching the T-%d entry:\n" % (len(due), ENTRY_LEAD))
    gos = []
    for d, t in due:
        r = evaluate(t)
        print_card(r)
        if r.get("verdict", "NO").startswith("GO"):
            gos.append(t)
    print("\n" + "=" * 72)
    print("GO list: %s" % (", ".join(gos) if gos else "(none)"))
    print("Sizing: 1-3%% of capital in PREMIUM per name, quarter-Kelly "
          "ceiling, f/N across concurrent positions.")
    print("Execute by hand as a single multi-leg straddle order. Never leg it.")


def cmd_log(args):
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "ticker", "ann_date", "action", "qty",
                        "quoted_bid", "quoted_ask", "mid", "limit_posted",
                        "fill_price", "phi_realized", "notes"])
        mid = 0.5 * (args.bid + args.ask)
        half = 0.5 * (args.ask - args.bid)
        phi = (abs(args.fill - mid) / half) if half > 0 else float("nan")
        w.writerow([datetime.now(timezone.utc).isoformat(), args.ticker,
                    args.ann_date, args.action, args.qty, args.bid, args.ask,
                    round(mid, 4), args.limit, args.fill, round(phi, 4),
                    args.notes or ""])
    print("logged %s %s %s  mid %.4f  fill %.4f  phi_realized %.3f"
          % (args.ticker, args.action, args.ann_date, mid, args.fill, phi))


def cmd_report(args):
    if not os.path.exists(LOG):
        print("no fills logged yet -- %s does not exist" % LOG)
        return
    import pandas as pd
    d = pd.read_csv(LOG)
    if d.empty:
        print("fill log is empty")
        return
    print("pilot fills: %d records, %d names" % (len(d), d["ticker"].nunique()))
    p = d["phi_realized"].dropna()
    print("\nREALISED PHI (ours, not the tape's):")
    print("  n=%d  median %.3f  mean %.3f  min %.3f  max %.3f"
          % (len(p), p.median(), p.mean(), p.min(), p.max()))
    print("\nbenchmarks from the $52.65 OPRA study (tape, last hour only):")
    print("  1-lot floor 0.393 | >=10 lots 0.456 | >=25 lots 0.583 | "
          "planning %.2f" % PHI_PLAN)
    if len(p) >= 5:
        v = "BETTER than plan" if p.median() < PHI_PLAN else "WORSE than plan"
        print("\n  -> our fills are %s (median %.3f vs %.2f)"
              % (v, p.median(), PHI_PLAN))
    else:
        print("\n  -> need >=5 fills before this comparison means anything")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("calendar").set_defaults(func=cmd_calendar)

    s = sub.add_parser("screen")
    s.add_argument("--ticker", required=True)
    s.add_argument("--earnings", default=None, help="YYYY-MM-DD override")
    s.add_argument("--session", default=None, choices=["AMC", "BMO"])
    s.set_defaults(func=cmd_screen)

    d = sub.add_parser("due")
    d.add_argument("--days", type=int, default=7)
    d.set_defaults(func=cmd_due)

    lg = sub.add_parser("log")
    lg.add_argument("--ticker", required=True)
    lg.add_argument("--ann-date", required=True, dest="ann_date")
    lg.add_argument("--action", required=True, choices=["entry", "exit"])
    lg.add_argument("--qty", type=int, required=True)
    lg.add_argument("--bid", type=float, required=True)
    lg.add_argument("--ask", type=float, required=True)
    lg.add_argument("--limit", type=float, required=True)
    lg.add_argument("--fill", type=float, required=True)
    lg.add_argument("--notes", default="")
    lg.set_defaults(func=cmd_log)

    sub.add_parser("report").set_defaults(func=cmd_report)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
