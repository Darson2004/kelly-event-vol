#!/usr/bin/env python
"""fetch_tcbbo.py -- BUDGET-BOUNDED OPRA tcbbo fetch for BLOCK-1 (P2 fill realism).

tcbbo = trades carrying the consolidated BBO at trade time. It is the only
schema on OPRA.PILLAR that can answer "would we actually have filled at mid",
because it pairs each print with the quote that stood when it printed.

SAFETY DESIGN -- this tool cannot overspend:
  * `ladder`  prices sample days and shows what several budgets would buy.
              No data, no spend.
  * `plan`    selects days greedily under a HARD --budget, then prices the
              SELECTED set EXACTLY (every day, not a sample) and writes the
              plan. Still no data, no spend.
  * `fetch`   refuses to run unless the plan's exact priced total is <=
              --budget, re-verifies the total against the API before the
              first byte, and stops mid-run if cumulative spend would breach
              the cap. Requires --i-approve-spending with the dollar figure.

Availability (verified 2026-09-01): tcbbo returns
data_schema_not_fully_available before ~2023-03-28, so only later events are
eligible.

Run: python fetch_tcbbo.py ...
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.join(HERE, "execution", "panel_liquid_v2.csv")
OUT_DIR = os.path.join(HERE, "data", "raw", "db_tcbbo")
DATASET = "OPRA.PILLAR"
SCHEMA = "tcbbo"
TCBBO_START = date(2023, 4, 3)      # first safely-available session
SAFETY_MARGIN = 0.95                # never plan above 95% of the stated budget


def client():
    try:
        import databento as db
    except ImportError:
        raise SystemExit("pip install databento")
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise SystemExit("no API key: set DATABENTO_API_KEY")
    return db.Historical(key)


def eligible_events(window: str, days_sel: str = "entry"):
    """One row per event: the days we would actually have traded.

    BUGFIX 2026-09-01: this used to test `window` (a TIME-OF-DAY setting,
    'near-close'|'full-day') against the string 'entry+exit', which it can
    never equal -- so the exit-day branch was dead code and the $52.65 fetch
    silently bought ENTRY DAYS ONLY. Day selection is now its own parameter.
    """
    p = pd.read_csv(PANEL, parse_dates=["ann_date", "entry_date", "exit_date"])
    p = p[p["lead_target"] == 14]
    p = p[p["entry_date"].dt.date >= TCBBO_START]
    ev = []
    for _, r in p.iterrows():
        days = []
        if days_sel in ("entry", "entry+exit"):
            days.append(r["entry_date"].date())
        if days_sel in ("exit", "entry+exit"):
            days.append(r["exit_date"].date())
        ev.append({"event_id": r["event_id"], "ticker": r["ticker"],
                   "ann_date": r["ann_date"].date().isoformat(),
                   "season": r["season"], "cost_frac": r["cost_frac"],
                   "days": sorted({d.isoformat() for d in days})})
    return ev


def stratify(ev):
    """Order events so any prefix is a balanced sample: round-robin across
    cost quintile x season, so a truncated budget still yields a
    representative panel rather than whichever names happen to sort first."""
    df = pd.DataFrame(ev)
    df["q"] = pd.qcut(df["cost_frac"].rank(method="first"), 5, labels=False)
    buckets = {}
    for (q, s), g in df.groupby(["q", "season"]):
        buckets.setdefault((q, s), list(g.index))
    order, keys = [], sorted(buckets)
    i = 0
    while any(buckets[k] for k in keys):
        k = keys[i % len(keys)]
        if buckets[k]:
            order.append(buckets[k].pop(0))
        i += 1
    return [ev[j] for j in order]


def day_symbol_map(events):
    m = {}
    for e in events:
        for d in e["days"]:
            m.setdefault(d, set()).add(e["ticker"])
    return m


def utc_window(d: str, window: str):
    """Exchange-local window -> UTC. MUST be DST-aware: 16:00 ET is 20:00 UTC
    under EDT but 21:00 UTC under EST, so a fixed UTC window silently misses
    the close for every winter event."""
    if window == "full-day":
        return d, (date.fromisoformat(d) + timedelta(days=1)).isoformat()
    et = ZoneInfo("America/New_York")
    day = date.fromisoformat(d)
    lo = datetime(day.year, day.month, day.day, 15, 0, tzinfo=et)
    hi = datetime(day.year, day.month, day.day, 16, 5, tzinfo=et)
    fmt = "%Y-%m-%dT%H:%M"
    return (lo.astimezone(timezone.utc).strftime(fmt),
            hi.astimezone(timezone.utc).strftime(fmt))


def price_day(cl, d, syms, window):
    start, end = utc_window(d, window)
    return float(cl.metadata.get_cost(
        dataset=DATASET, schema=SCHEMA, start=start, end=end,
        symbols=[s + ".OPT" for s in sorted(syms)], stype_in="parent"))


def cmd_ladder(args):
    cl = client()
    ev = stratify(eligible_events(args.window, args.days_sel))
    dm = day_symbol_map(ev)
    days = sorted(dm)
    symdays = sum(len(v) for v in dm.values())
    print("eligible: %d events (tcbbo era), %d distinct days, %d symbol-days"
          % (len(ev), len(days), symdays))
    idx = list(pd.Series(range(len(days))).sample(
        min(args.sample, len(days)), random_state=11).sort_values())
    per = []
    for i in idx:
        d = days[int(i)]
        try:
            c = price_day(cl, d, dm[d], args.window)
            per.append(c / len(dm[d]))
            print("  %s %2d syms $%7.4f  ($%.4f/sym-day)"
                  % (d, len(dm[d]), c, c / len(dm[d])))
        except Exception as exc:                                # noqa: BLE001
            print("  %s ERROR %s" % (d, str(exc).split("\n")[0]))
    if not per:
        raise SystemExit("could not price any day")
    per.sort()
    lo, mid, hi = per[0], per[len(per) // 2], per[-1]
    mean = sum(per) / len(per)
    print("\n$/symbol-day  min %.4f  median %.4f  mean %.4f  max %.4f (n=%d)"
          % (lo, mid, mean, hi, len(per)))
    print("full eligible set: %d sym-days -> $%.2f (at mean); range $%.2f-$%.2f"
          % (symdays, mean * symdays, lo * symdays, hi * symdays))
    print("\nWhat a budget buys (events, stratified; ~%.1f sym-days/event):"
          % (symdays / max(len(ev), 1)))
    spe = symdays / max(len(ev), 1)
    for b in args.budgets:
        n_sd = b * SAFETY_MARGIN / mean
        print("  $%-7.0f -> ~%4d symbol-days  ~%4d events  (worst case ~%3d)"
              % (b, n_sd, n_sd / spe, (b * SAFETY_MARGIN / hi) / spe))
    print("\nNo data fetched, nothing billed. Next: `plan --budget N`.")


def cmd_plan(args):
    cl = client()
    ev = stratify(eligible_events(args.window, args.days_sel))
    cap = args.budget * SAFETY_MARGIN
    chosen, dm, total, priced = [], {}, 0.0, {}
    for e in ev:
        trial = {k: set(v) for k, v in dm.items()}
        for d in e["days"]:
            trial.setdefault(d, set()).add(e["ticker"])
        newtotal, ok = 0.0, True
        for d, syms in trial.items():
            k = (d, tuple(sorted(syms)))
            if k not in priced:
                try:
                    priced[k] = price_day(cl, d, syms, args.window)
                except Exception:                               # noqa: BLE001
                    ok = False
                    break
            newtotal += priced[k]
        if not ok:
            continue
        if newtotal > cap:
            break
        dm, total = trial, newtotal
        chosen.append(e)
        print("  +%-6s %s  running $%.2f / cap $%.2f (%d events)"
              % (e["ticker"], e["ann_date"], total, cap, len(chosen)))
    plan = {"config": {"dataset": DATASET, "schema": SCHEMA,
                       "window": args.window, "budget": args.budget,
                       "cap_after_margin": round(cap, 2),
                       "exact_priced_total": round(total, 4),
                       "created": date.today().isoformat()},
            "events": [e["event_id"] for e in chosen],
            "days": {d: sorted(s) for d, s in dm.items()}}
    with open(args.out, "w") as f:
        json.dump(plan, f, indent=2)
    print("\nPLAN: %d events, %d days, EXACT priced total $%.2f (cap $%.2f)"
          % (len(chosen), len(dm), total, cap))
    print("wrote %s -- still nothing fetched, nothing billed." % args.out)


def cmd_fetch(args):
    plan = json.load(open(args.plan))
    cfg = plan["config"]
    exact = float(cfg["exact_priced_total"])
    if args.i_approve_spending is None:
        raise SystemExit("REFUSED: pass --i-approve-spending <USD> to confirm")
    if exact > args.i_approve_spending:
        raise SystemExit("REFUSED: plan costs $%.2f > approved $%.2f"
                         % (exact, args.i_approve_spending))
    cl = client()
    os.makedirs(OUT_DIR, exist_ok=True)
    spent = 0.0
    days = sorted(plan["days"])
    print("re-verifying prices against the API before any download...")
    for d in days:
        spent += price_day(cl, d, set(plan["days"][d]), cfg["window"])
    if spent > args.i_approve_spending:
        raise SystemExit("REFUSED: re-verified cost $%.2f exceeds approved $%.2f"
                         % (spent, args.i_approve_spending))
    print("re-verified total $%.2f <= approved $%.2f. fetching.\n"
          % (spent, args.i_approve_spending))
    run = 0.0
    for i, d in enumerate(days, 1):
        syms = [s + ".OPT" for s in plan["days"][d]]
        out = os.path.join(OUT_DIR, "%s.csv.gz" % d)
        if os.path.exists(out):
            print("  [%d/%d] %s cached" % (i, len(days), d))
            continue
        c = price_day(cl, d, set(plan["days"][d]), cfg["window"])
        if run + c > args.i_approve_spending:
            print("STOPPING: next day would breach the approved cap.")
            break
        start, end = utc_window(d, cfg["window"])
        data = cl.timeseries.get_range(
            dataset=DATASET, schema=SCHEMA, start=start, end=end,
            symbols=syms, stype_in="parent")
        df = data.to_df()
        with gzip.open(out, "wt") as f:
            df.to_csv(f, index=False)
        run += c
        print("  [%d/%d] %s %d syms %d rows $%.4f (run $%.2f)"
              % (i, len(days), d, len(syms), len(df), c, run))
    print("\ndone. spent ~$%.2f of approved $%.2f"
          % (run, args.i_approve_spending))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("ladder", cmd_ladder), ("plan", cmd_plan),
                     ("fetch", cmd_fetch)):
        s = sub.add_parser(name)
        s.add_argument("--window", default="near-close",
                       choices=["near-close", "full-day"])
        s.add_argument("--days", default="entry", dest="days_sel",
                       choices=["entry", "exit", "entry+exit"],
                       help="which trading days per event (see BUGFIX note)")
        if name == "ladder":
            s.add_argument("--sample", type=int, default=10)
            s.add_argument("--budgets", type=float, nargs="+",
                           default=[25, 50, 100, 184, 300])
        if name == "plan":
            s.add_argument("--budget", type=float, required=True)
            s.add_argument("--out", default=os.path.join(
                HERE, "data", "db_plan_tcbbo.json"))
        if name == "fetch":
            s.add_argument("--plan", required=True)
            s.add_argument("--i-approve-spending", type=float, default=None)
        s.set_defaults(func=fn)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
