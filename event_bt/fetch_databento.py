#!/usr/bin/env python
"""fetch_databento.py -- build canonical chains.csv from Databento OPRA.

Pipeline (each step resumable; no API key needed until `cost`/`fetch`):

  1. prep-events  Bloomberg earnings export -> data/canonical/events.csv
  2. plan         events -> request plan (one request per trading day,
                  parent symbols batched; window T-20..T+3 per event)
  3. cost         PRICE THE PLAN before spending: metadata.get_cost over a
                  sample of days, extrapolated (--full for exact). No data
                  is downloaded and nothing is billed by this step.
  4. fetch        execute the plan -> data/raw/db_cbbo/<date>.csv.gz
                  (cbbo-1m last-NBBO bars, ~15:44-15:48 ET window)
  5. assemble     cached days -> canonical chains.csv
                  (OSI parsing, last bar per contract, parity-implied spot)
  6. selftest     no-network end-to-end check of steps 5's math

Then: bt.py validate / bt.py run  (see DATA_SPEC.md).

Data facts (verified 2026-08-16): OPRA.PILLAR cbbo-1m history starts
2013-04-01; full-resolution schemas only 2023-03-28+. cbbo-1m carries the
last consolidated NBBO + last sale per interval, per contract. Spot is NOT
in the options feed -- we derive the forward from put-call parity at the
nearest expiry (median of C_mid - P_mid + K over the 5 most ATM strikes),
which is exactly the r=0 'spot' the engine wants.

Run:
  python fetch_databento.py ...
API key: --key or env DATABENTO_API_KEY.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import glob
import gzip
import json
import math
import os
import re
import sys
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATASET = "OPRA.PILLAR"
SCHEMA = "cbbo-1m"
HISTORY_START = date(2013, 4, 1)
CACHE_DIR = os.path.join(HERE, "data", "raw", "db_cbbo")
CANON_DIR = os.path.join(HERE, "data", "canonical")
PLAN_FILE = os.path.join(HERE, "data", "db_plan.json")

OSI_RE = re.compile(r"^([A-Z0-9]{1,6})\s*(\d{6})([CP])(\d{8})$")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def opra_root(ticker: str) -> str:
    """Normalize a ticker to its OPRA root form (BRK/B -> BRKB)."""
    return re.sub(r"[^A-Z0-9]", "", str(ticker).upper().strip())


def parse_osi(sym: str):
    """OSI 21-char option symbol -> (root, expiry, cp, strike) or None."""
    m = OSI_RE.match(str(sym).strip())
    if not m:
        return None
    root, ymd, cp, k = m.groups()
    try:
        exp = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    except ValueError:
        return None
    return root, exp, cp, int(k) / 1000.0


def et_window_utc(d: date, snap: str, width_min: int):
    """(start_utc, end_utc) ISO strings for a snap window on day d, ET."""
    from zoneinfo import ZoneInfo
    hh, mm = (int(x) for x in snap.split(":"))
    et = ZoneInfo("America/New_York")
    center = datetime(d.year, d.month, d.day, hh, mm, tzinfo=et)
    lo = center - timedelta(minutes=width_min // 2)
    hi = center + timedelta(minutes=width_min - width_min // 2)
    fmt = "%Y-%m-%dT%H:%M:%S"
    return (lo.astimezone(ZoneInfo("UTC")).strftime(fmt) + "Z",
            hi.astimezone(ZoneInfo("UTC")).strftime(fmt) + "Z")


def _client(args):
    try:
        import databento as db
    except ImportError:
        raise SystemExit("pip install databento")
    key = args.key or os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise SystemExit("no API key: pass --key or set DATABENTO_API_KEY")
    return db.Historical(key)


def _pick_col(df: pd.DataFrame, names) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    return None


# ---------------------------------------------------------------------------
# 1. prep-events: Bloomberg export -> canonical events.csv
# ---------------------------------------------------------------------------

def cmd_prep_events(args) -> None:
    raw = pd.read_csv(args.raw, encoding="utf-8-sig")
    cols = {c.lower().strip(): c for c in raw.columns}
    if "eventdate" in cols and "earningsperiod" in cols:
        # Bloomberg export: "ACT UW Equity", eventDate, callTime, earningsPeriod
        tk = raw[cols.get("ticker", "ticker")].astype(str).str.split().str[0]
        df = pd.DataFrame({
            "ticker": tk.map(opra_root),
            "ann_date": pd.to_datetime(raw[cols["eventdate"]],
                                       errors="coerce").dt.date,
            "session": raw[cols["earningsperiod"]].astype(str).str.upper().str.strip(),
        })
    else:  # generic layouts -> reuse the ingest matcher
        from ingest import load_events
        df = load_events(args.raw)
        df["ticker"] = df["ticker"].map(opra_root)

    n0 = len(df)
    df = df.dropna(subset=["ann_date"])
    dm = int((~df["session"].isin(["BMO", "AMC"])).sum())
    df = df[df["session"].isin(["BMO", "AMC"])]
    df = df.drop_duplicates(subset=["ticker", "ann_date"]).sort_values(
        ["ticker", "ann_date"])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)
    print("events: %d in -> %d kept (%d dropped: intraday/'DM' session or "
          "bad date)" % (n0, len(df), n0 - len(df)))
    print("  %d tickers | %s .. %s | sessions %s"
          % (df["ticker"].nunique(), df["ann_date"].min(), df["ann_date"].max(),
             df["session"].value_counts().to_dict()))
    if dm:
        print("  note: intraday ('DM') announcements are untradeable with a "
              "close-snapshot design and were dropped")
    print("wrote %s" % args.out)


# ---------------------------------------------------------------------------
# 2. plan: events -> {day: [parents]} request plan
# ---------------------------------------------------------------------------

def cmd_plan(args) -> None:
    ev = pd.read_csv(args.events)
    ev["ann_date"] = pd.to_datetime(ev["ann_date"]).dt.date
    ev["ticker"] = ev["ticker"].map(opra_root)
    if args.tickers:
        keep = {opra_root(t) for t in args.tickers.split(",")}
        ev = ev[ev["ticker"].isin(keep)]
    lo_cap = max(HISTORY_START, pd.to_datetime(args.start).date()
                 if args.start else HISTORY_START)
    hi_cap = (pd.to_datetime(args.end).date() if args.end
              else date.today() - timedelta(days=1))

    days: dict[str, set] = {}
    n_events = 0
    for _, r in ev.iterrows():
        ann = r["ann_date"]
        if ann - timedelta(days=args.pre) > hi_cap or ann < lo_cap:
            continue
        n_events += 1
        d = ann - timedelta(days=args.pre)
        while d <= ann + timedelta(days=args.post):
            if d.weekday() < 5 and lo_cap <= d <= hi_cap:
                days.setdefault(d.isoformat(), set()).add(r["ticker"])
            d += timedelta(days=1)

    plan = {"config": {"dataset": DATASET, "schema": SCHEMA,
                       "snap": args.snap, "width_min": args.width,
                       "pre": args.pre, "post": args.post,
                       "events_file": os.path.abspath(args.events),
                       "created": date.today().isoformat()},
            "days": {k: sorted(v) for k, v in sorted(days.items())}}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(plan, fh)
    sym_days = sum(len(v) for v in days.values())
    print("plan: %d events -> %d request-days, %d symbol-days "
          "(window T-%d..T+%d, snap %s ET +/- %d min)"
          % (n_events, len(days), sym_days, args.pre, args.post,
             args.snap, args.width // 2))
    print("wrote %s" % args.out)
    print("next: `cost` to price it (no download), then `fetch`")


def _load_plan(path: str) -> dict:
    if not os.path.exists(path):
        raise SystemExit("no plan at %s -- run `plan` first" % path)
    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# 3. cost: price the plan without downloading
# ---------------------------------------------------------------------------

def cmd_cost(args) -> None:
    plan = _load_plan(args.plan)
    client = _client(args)
    cfg = plan["config"]
    items = list(plan["days"].items())
    if not items:
        raise SystemExit("plan has no days")
    if args.full or len(items) <= args.sample:
        picks = list(range(len(items)))
    else:  # evenly spaced sample across the whole span
        picks = list(np.linspace(0, len(items) - 1, args.sample).astype(int))
    tot_sym_days = sum(len(v) for _, v in items)

    cost_s, sym_s = 0.0, 0
    for i, pi in enumerate(picks):
        day, parents = items[pi]
        lo, hi = et_window_utc(date.fromisoformat(day), cfg["snap"],
                               cfg["width_min"])
        try:
            c = client.metadata.get_cost(
                dataset=cfg["dataset"], symbols=[p + ".OPT" for p in parents],
                schema=cfg["schema"], start=lo, end=hi, stype_in="parent")
        except Exception as e:
            print("  %s: cost query failed (%s)" % (day, e))
            continue
        cost_s += float(c)
        sym_s += len(parents)
        if (i + 1) % 10 == 0:
            print("  ...%d/%d days sampled, running $%.2f"
                  % (i + 1, len(picks), cost_s))
    if sym_s == 0:
        raise SystemExit("all cost queries failed -- check key / connectivity")
    est = cost_s * (tot_sym_days / sym_s)
    tag = "EXACT" if (args.full or len(picks) == len(items)) else \
        "estimate from %d/%d days" % (len(picks), len(items))
    print("plan cost: $%.2f (%s) for %d request-days, %d symbol-days"
          % (est, tag, len(items), tot_sym_days))
    print("(billed only when `fetch` runs; already-cached days are skipped)")


# ---------------------------------------------------------------------------
# 4. fetch: execute the plan with caching + retries
# ---------------------------------------------------------------------------

KEEP_BID = ["bid_px_00", "bid_px", "bid"]
KEEP_ASK = ["ask_px_00", "ask_px", "ask"]
KEEP_SYM = ["symbol", "raw_symbol"]


def _fetch_day(client, cfg, day: str, parents: list, verbose_first: list,
               cache_dir: str):
    out = os.path.join(cache_dir, "%s.csv.gz" % day)
    if os.path.exists(out):
        return day, "cached", 0
    lo, hi = et_window_utc(date.fromisoformat(day), cfg["snap"],
                           cfg["width_min"])
    # chunk the symbol list: single requests with many hundreds of parents
    # can 504 at the gateway on peak earnings days
    chunk = 150
    parts, last_err = [], None
    for j in range(0, len(parents), chunk):
        batch = [p + ".OPT" for p in parents[j:j + chunk]]
        for attempt in range(3):
            try:
                store = client.timeseries.get_range(
                    dataset=cfg["dataset"], schema=cfg["schema"],
                    symbols=batch, start=lo, end=hi, stype_in="parent")
                parts.append(store.to_df())
                break
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if "no data" in msg or "422" in msg or "did not resolve" in msg:
                    break
                time.sleep(4 * (attempt + 1))
        else:
            return day, "ERROR: %s" % last_err, 0
    parts = [p for p in parts if p is not None and not p.empty]
    df = pd.concat(parts) if parts else pd.DataFrame()

    if df is None or df.empty:
        pd.DataFrame(columns=["ts_event", "symbol", "bid", "ask"]).to_csv(
            out, index=False, compression="gzip")
        return day, "empty", 0

    df = df.reset_index()
    if verbose_first and not verbose_first[0]:
        verbose_first[0] = True
        print("  [first day column check] %s" % list(df.columns))
    sym = _pick_col(df, KEEP_SYM)
    bid = _pick_col(df, KEEP_BID)
    ask = _pick_col(df, KEEP_ASK)
    # use whichever timestamp column is actually populated (ts_event comes
    # back mostly null from cbbo to_df; ts_recv carries the real times)
    cands = [c for c in ("ts_event", "ts_recv", "index") if c in df.columns]
    ts = max(cands, key=lambda c: df[c].notna().sum()) if cands else None
    if ts is not None and df[ts].notna().sum() == 0:
        ts = None
    if not (sym and bid and ask and ts):
        return day, "ERROR: unexpected columns %s" % list(df.columns), 0
    slim = df[[ts, sym, bid, ask]].copy()
    slim.columns = ["ts_event", "symbol", "bid", "ask"]
    # fixed-precision guard: databento sentinel/int prices
    for c in ("bid", "ask"):
        slim[c] = pd.to_numeric(slim[c], errors="coerce")
        big = slim[c].abs() > 1e6
        slim.loc[big, c] = slim.loc[big, c] / 1e9
    # write-then-rename so a killed process never leaves a truncated cache
    tmp = out + ".tmp"
    slim.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, out)
    return day, "ok", len(slim)


def plan_cache_dir(plan_path: str) -> str:
    """Per-plan cache dir: different plans have different symbol sets for the
    same date, so day-keyed files must not be shared across plans."""
    name = os.path.splitext(os.path.basename(plan_path))[0]
    return os.path.join(CACHE_DIR, name)


def cmd_fetch(args) -> None:
    plan = _load_plan(args.plan)
    client = _client(args)
    cfg = plan["config"]
    cache_dir = plan_cache_dir(args.plan)
    os.makedirs(cache_dir, exist_ok=True)
    items = list(plan["days"].items())
    if args.limit:
        items = items[: args.limit]
    todo = [(d, p) for d, p in items
            if not os.path.exists(os.path.join(cache_dir, "%s.csv.gz" % d))]
    print("fetch: %d days in plan, %d already cached, %d to pull, "
          "%d workers -> %s" % (len(items), len(items) - len(todo), len(todo),
                                args.workers, cache_dir))
    verbose_first = [False]
    n_ok = n_err = rows = 0
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_fetch_day, client, cfg, d, p, verbose_first,
                          cache_dir): d
                for d, p in todo}
        for i, fut in enumerate(cf.as_completed(futs)):
            day, status, n = fut.result()
            if status.startswith("ERROR"):
                n_err += 1
                print("  %s %s" % (day, status))
            else:
                n_ok += 1
                rows += n
            if (i + 1) % 50 == 0:
                el = time.time() - t0
                print("  %d/%d days (%.0f s, %.1f d/s, %d rows, %d errors)"
                      % (i + 1, len(todo), el, (i + 1) / max(el, 1e-9),
                         rows, n_err))
    print("done: %d ok, %d errors, %d rows -> %s" % (n_ok, n_err, rows,
                                                     cache_dir))
    if n_err:
        print("rerun `fetch` to retry the failed days (cached days skip).")


# ---------------------------------------------------------------------------
# 5. assemble: cache -> canonical chains.csv
# ---------------------------------------------------------------------------

def parity_spot(day_root: pd.DataFrame) -> float:
    """Forward from put-call parity: median of C_mid - P_mid + K over the 5
    most-ATM strikes of the nearest expiry with >=3 call/put pairs."""
    for exp in sorted(day_root["expiry"].unique()):
        g = day_root[day_root["expiry"] == exp]
        c = g[g["cp"] == "C"].set_index("strike")[["mid"]]
        p = g[g["cp"] == "P"].set_index("strike")[["mid"]]
        j = c.join(p, lsuffix="_c", rsuffix="_p", how="inner").dropna()
        j = j[(j["mid_c"] > 0) & (j["mid_p"] > 0)]
        if len(j) < 3:
            continue
        j["gap"] = (j["mid_c"] - j["mid_p"]).abs()
        j = j.nsmallest(5, "gap")
        s = float(np.median(j["mid_c"] - j["mid_p"] + j.index.values))
        if s > 0.5:
            return s
    return float("nan")


def assemble_day(path: str, max_dte: int, band: float) -> list[dict]:
    day = date.fromisoformat(os.path.basename(path)[:10])
    raw = pd.read_csv(path, compression="gzip")
    if raw.empty:
        return []
    # last bar per contract within the snap window (stable sort: rows with
    # equal/NaN timestamps keep their chronological arrival order)
    raw = raw.sort_values("ts_event", kind="stable").groupby(
        "symbol", as_index=False).last()
    parsed = raw["symbol"].map(parse_osi)
    ok = parsed.notna()
    raw, parsed = raw[ok], parsed[ok]
    if raw.empty:
        return []
    raw = raw.assign(root=[p[0] for p in parsed],
                     expiry=[p[1] for p in parsed],
                     cp=[p[2] for p in parsed],
                     strike=[p[3] for p in parsed])
    raw["bid"] = raw["bid"].clip(lower=0)
    raw = raw[(raw["ask"] > 0) & (raw["ask"] >= raw["bid"])]
    raw["mid"] = 0.5 * (raw["bid"] + raw["ask"])
    raw["dte"] = raw["expiry"].map(lambda e: (e - day).days)
    raw = raw[(raw["dte"] >= 1) & (raw["dte"] <= max_dte)]

    rows = []
    for root, g in raw.groupby("root"):
        spot = parity_spot(g)
        if math.isnan(spot):
            continue
        g = g[(g["strike"] >= spot * (1 - band)) &
              (g["strike"] <= spot * (1 + band))]
        c = g[g["cp"] == "C"].set_index(["expiry", "strike"])
        p = g[g["cp"] == "P"].set_index(["expiry", "strike"])
        j = c[["bid", "ask"]].join(p[["bid", "ask"]], lsuffix="_c",
                                   rsuffix="_p", how="inner")
        for (exp, k), r in j.iterrows():
            rows.append({"obs_date": day.isoformat(), "ticker": root,
                         "expiry": exp.isoformat() if hasattr(exp, "isoformat")
                         else str(exp),
                         "spot": round(spot, 4), "strike": k,
                         "call_bid": r["bid_c"], "call_ask": r["ask_c"],
                         "put_bid": r["bid_p"], "put_ask": r["ask_p"]})
    return rows


def cmd_assemble(args) -> None:
    files = sorted(glob.glob(os.path.join(args.cache, "*.csv.gz")))
    if not files:
        raise SystemExit("no cached days in %s -- run `fetch` first" % args.cache)
    # checkpointed: one partial per day, so an interrupted run resumes
    part_dir = os.path.join(args.cache, "_assembled")
    os.makedirs(part_dir, exist_ok=True)
    n_new = 0
    for i, f in enumerate(files):
        part = os.path.join(part_dir, os.path.basename(f))
        if os.path.exists(part):
            continue
        rows = assemble_day(f, args.max_dte, args.band)
        pd.DataFrame(rows).to_csv(part, index=False, compression="gzip")
        n_new += 1
        if n_new % 50 == 0:
            print("  ...assembled %d new days (at %d/%d)" % (n_new, i + 1,
                                                             len(files)))
    parts = sorted(glob.glob(os.path.join(part_dir, "*.csv.gz")))
    frames = []
    for p in parts:
        try:
            x = pd.read_csv(p)
        except pd.errors.EmptyDataError:
            continue
        if not x.empty:
            frames.append(x)
    n_empty = len(parts) - len(frames)
    if not frames:
        raise SystemExit("no usable rows -- check cache contents")
    out = pd.concat(frames, ignore_index=True).sort_values(
        ["ticker", "obs_date", "expiry", "strike"])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out.to_csv(args.out, index=False)
    print("chains: %d rows | %d tickers | %s .. %s | %d/%d days empty"
          % (len(out), out["ticker"].nunique(), out["obs_date"].min(),
             out["obs_date"].max(), n_empty, len(files)))
    med_spread = ((out["call_ask"] - out["call_bid"] + out["put_ask"]
                   - out["put_bid"]) /
                  (0.5 * (out["call_ask"] + out["call_bid"] + out["put_ask"]
                          + out["put_bid"])).clip(lower=1e-9)).median()
    print("median straddle spread/mid: %.1f%%" % (100 * med_spread))
    print("wrote %s" % args.out)
    print("next: bt.py validate, then bt.py run --entry-target 14,7,3")


# ---------------------------------------------------------------------------
# 6. selftest: no-network check of OSI parsing + parity spot + assembly
# ---------------------------------------------------------------------------

def cmd_selftest(args) -> None:
    import engine
    tmp = os.path.join(HERE, "_synth_db")
    os.makedirs(tmp, exist_ok=True)
    day, spot0, sigma = date(2025, 3, 10), 187.35, 0.42
    move = 0.06
    exps = [date(2025, 3, 21), date(2025, 4, 4)]   # pre-event, post-event
    ann = date(2025, 3, 25)
    rows = []
    for exp in exps:
        dte = (exp - day).days
        has_evt = exp > ann
        var = (move / engine.C_ABS) ** 2 * (1 if has_evt else 0) \
            + sigma ** 2 * (dte - (1 if has_evt else 0)) / 365.0
        iv = math.sqrt(var / (dte / 365.0))
        for k in range(150, 226, 5):
            for cp in "CP":
                px = engine.bs_price(spot0, k, dte / 365.0, iv,
                                     "c" if cp == "C" else "p")
                w = max(0.04 * px, 0.02)
                sym = "%-6s%s%s%08d" % ("FAKE", exp.strftime("%y%m%d"),
                                        cp, int(k * 1000))
                rows.append({"ts_event": "2025-03-10T19:46:00Z",
                             "symbol": sym, "bid": max(px - w / 2, 0),
                             "ask": px + w / 2})
    path = os.path.join(tmp, "%s.csv.gz" % day.isoformat())
    pd.DataFrame(rows).to_csv(path, index=False, compression="gzip")

    got = pd.DataFrame(assemble_day(path, 60, 0.30))
    checks = []
    p = parse_osi("FAKE  250404C00185000")
    checks.append(("OSI parse", p == ("FAKE", date(2025, 4, 4), "C", 185.0),
                   str(p)))
    sp = got["spot"].iloc[0] if len(got) else float("nan")
    checks.append(("parity spot", abs(sp / spot0 - 1) < 0.005,
                   "%.2f vs planted %.2f" % (sp, spot0)))
    checks.append(("both expiries present",
                   set(got["expiry"].unique()) ==
                   {e.isoformat() for e in exps}, str(sorted(
                       got["expiry"].unique()))))
    day_slice = got.copy()
    day_slice["expiry"] = pd.to_datetime(day_slice["expiry"]).dt.date
    day_slice["call_iv"] = np.nan
    day_slice["put_iv"] = np.nan
    im, amb, ivp, epost, epre = engine.implied_move_at(
        day_slice, sp, day, pre_ok=ann, capture=ann + timedelta(days=1))
    checks.append(("implied move recovered",
                   not math.isnan(im) and abs(im / move - 1) < 0.10,
                   "%.4f vs planted %.4f" % (im, move)))
    ok = True
    for name, passed, detail in checks:
        print("  [%s] %-28s %s" % ("PASS" if passed else "FAIL", name, detail))
        ok &= passed
    if not ok:
        raise SystemExit("DATABENTO-PATH SELFTEST FAILED")
    print("DATABENTO-PATH SELFTEST PASSED -- assembly math verified; "
          "ready for a real API key.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--key", default=None, help="Databento API key "
                                               "(or env DATABENTO_API_KEY)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("prep-events", help="Bloomberg export -> events.csv")
    s.add_argument("--raw", required=True)
    s.add_argument("--out", default=os.path.join(CANON_DIR, "events.csv"))
    s.set_defaults(func=cmd_prep_events)

    s = sub.add_parser("plan", help="events -> request plan")
    s.add_argument("--events", default=os.path.join(CANON_DIR, "events.csv"))
    s.add_argument("--tickers", default=None, help="comma list to restrict "
                                                   "universe (pilot!)")
    s.add_argument("--start", default=None, help="clamp events >= this date")
    s.add_argument("--end", default=None)
    s.add_argument("--pre", type=int, default=20, help="days before ann")
    s.add_argument("--post", type=int, default=3, help="days after ann")
    s.add_argument("--snap", default="15:46", help="ET snapshot minute")
    s.add_argument("--width", type=int, default=4, help="window minutes")
    s.add_argument("--out", default=PLAN_FILE)
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("cost", help="price the plan (no download, no charge)")
    s.add_argument("--plan", default=PLAN_FILE)
    s.add_argument("--sample", type=int, default=40)
    s.add_argument("--full", action="store_true", help="cost every day exactly")
    s.set_defaults(func=cmd_cost)

    s = sub.add_parser("fetch", help="execute the plan (resumable)")
    s.add_argument("--plan", default=PLAN_FILE)
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--limit", type=int, default=0,
                   help="only first N days (smoke test)")
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("assemble", help="cache -> canonical chains.csv")
    s.add_argument("--cache", default=CACHE_DIR)
    s.add_argument("--max-dte", type=int, default=60)
    s.add_argument("--band", type=float, default=0.30,
                   help="strike band around spot (0.30 = +/-30%%; do not "
                        "narrow -- see DATA_SPEC truncation warning)")
    s.add_argument("--out", default=os.path.join(CANON_DIR, "chains.csv"))
    s.set_defaults(func=cmd_assemble)

    s = sub.add_parser("selftest", help="no-network assembly verification")
    s.set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
