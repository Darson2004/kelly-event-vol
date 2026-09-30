#!/usr/bin/env python
"""ingest.py -- normalize vendor option data into the canonical schema.

Canonical outputs (written to --out, default data/canonical/):
  events.csv  ticker, ann_date, session
  chains.csv  obs_date, ticker, expiry, spot, strike,
              call_bid, call_ask, put_bid, put_ask [, call_iv, put_iv]

Vendors:
  orats     ORATS historical strikes files (hist/strikes API or bulk CSVs).
            Column names are matched case-insensitively against known ORATS
            names; anything missing is reported explicitly.
  generic   Any CSV plus a JSON column map: {"obs_date": "your_col", ...}.
            Use this for ThetaData / Polygon / CBOE DataShop exports.

Events can come from a vendor earnings file (--events-file with
ticker/date/session columns, flexible names) -- always required, since
chains alone don't carry announcement timestamps.

Rows are trimmed to event windows (T-25 .. T+5) and strikes within
+/- 20% of spot to keep the canonical file small.
"""

from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd

# known vendor spellings, all compared lower-cased
ORATS_STRIKES = {
    "obs_date": ["tradedate", "trade_date", "quotedate", "quote_date"],
    "ticker": ["ticker", "symbol", "underlying"],
    "expiry": ["expirdate", "expirationdate", "expiration", "expiry"],
    "spot": ["stockprice", "stkpx", "underlyingprice", "stock_price",
             "spotprice", "spot_px", "spotpx"],
    "strike": ["strike", "strikeprice"],
    "call_bid": ["callbidprice", "cbidpx", "call_bid", "callbid"],
    "call_ask": ["callaskprice", "caskpx", "call_ask", "callask"],
    "put_bid": ["putbidprice", "pbidpx", "put_bid", "putbid"],
    "put_ask": ["putaskprice", "paskpx", "put_ask", "putask"],
    "call_iv": ["callmidiv", "cmidiv", "call_iv", "smoothsmvvol"],
    "put_iv": ["putmidiv", "pmidiv", "put_iv"],
}
EVENT_COLS = {
    "ticker": ["ticker", "symbol", "act_symbol"],
    "ann_date": ["ann_date", "earndate", "earningsdate", "earnings_date",
                 "date", "reportdate", "report_date", "anndate"],
    "session": ["session", "annctod", "anntime", "ann_time", "time", "timing",
                "when", "bmo_amc", "timeofday"],
}
OPTIONAL_CHAIN = ("call_iv", "put_iv")


def _match_cols(df: pd.DataFrame, spec: dict, label: str,
                optional=()) -> dict:
    lower = {c.lower().strip(): c for c in df.columns}
    out, missing = {}, []
    for canon, names in spec.items():
        hit = next((lower[n] for n in names if n in lower), None)
        if hit is None and canon.lower() in lower:
            hit = lower[canon.lower()]
        if hit is None:
            if canon not in optional:
                missing.append(canon)
        else:
            out[canon] = hit
    if missing:
        raise SystemExit(
            "%s: could not find columns for %s.\nAvailable columns: %s\n"
            "Fix: pass --map map.json with {\"%s\": \"<your column>\", ...}"
            % (label, missing, list(df.columns), missing[0]))
    return out


def _normalize_session(s: pd.Series) -> pd.Series:
    v = s.astype(str).str.strip().str.upper()
    out = pd.Series("UNK", index=s.index)
    out[v.str.contains("BEFORE|BMO|PRE|MORNING|^AM$", regex=True, na=False)] = "BMO"
    out[v.str.contains("AFTER|AMC|POST|EVENING|^PM$", regex=True, na=False)] = "AMC"
    out[v.isin(["BMO", "AMC"])] = v[v.isin(["BMO", "AMC"])]
    # ORATS anncTod style: time-of-day like "0800" / "1630" / "735"
    tod = pd.to_numeric(v.str.replace(":", "", regex=False), errors="coerce")
    out[(tod >= 0) & (tod < 930)] = "BMO"
    out[(tod >= 1555) & (tod <= 2359)] = "AMC"
    # 09:30-15:55 = intraday announcement -> leave UNK (drop in validate)
    return out


def load_events(events_file: str, colmap: dict | None = None) -> pd.DataFrame:
    df = pd.read_csv(events_file)
    m = colmap or _match_cols(df, EVENT_COLS, "events", optional=("session",))
    out = pd.DataFrame({
        "ticker": df[m["ticker"]].astype(str).str.upper().str.strip(),
        "ann_date": pd.to_datetime(df[m["ann_date"]]).dt.date,
    })
    out["session"] = (_normalize_session(df[m["session"]])
                      if "session" in m else "UNK")
    out = out.dropna(subset=["ann_date"]).drop_duplicates(
        subset=["ticker", "ann_date"]).sort_values(["ticker", "ann_date"])
    return out.reset_index(drop=True)


def ingest_chains(raw: str, vendor: str, events: pd.DataFrame,
                  colmap_file: str | None = None,
                  atm_band: float = 0.20, window=(25, 5)) -> pd.DataFrame:
    files = sorted(glob.glob(raw)) if any(ch in raw for ch in "*?[") else None
    if files is None:
        files = (sorted(glob.glob(os.path.join(raw, "**", "*.csv"),
                                  recursive=True))
                 if os.path.isdir(raw) else [raw])
    if not files:
        raise SystemExit("no input files matched: %s" % raw)
    user_map = json.load(open(colmap_file)) if colmap_file else None

    # per-ticker event windows for trimming
    ev = events.copy()
    ev["lo"] = pd.to_datetime(ev["ann_date"]) - pd.Timedelta(days=window[0])
    ev["hi"] = pd.to_datetime(ev["ann_date"]) + pd.Timedelta(days=window[1])
    windows = {t: list(zip(g["lo"], g["hi"])) for t, g in ev.groupby("ticker")}

    chunks = []
    for i, f in enumerate(files):
        df = pd.read_csv(f)
        if df.empty:
            continue
        if user_map:
            m = {k: v for k, v in user_map.items() if v in df.columns}
            need = [k for k in ORATS_STRIKES if k not in m
                    and k not in OPTIONAL_CHAIN]
            if need:
                raise SystemExit("column map missing canonical keys %s for %s"
                                 % (need, f))
        else:
            m = _match_cols(df, ORATS_STRIKES, os.path.basename(f),
                            optional=OPTIONAL_CHAIN)
        sub = pd.DataFrame({k: df[v] for k, v in m.items()})
        sub["ticker"] = sub["ticker"].astype(str).str.upper().str.strip()
        sub["obs_date"] = pd.to_datetime(sub["obs_date"])
        sub["expiry"] = pd.to_datetime(sub["expiry"])
        for c in ("spot", "strike", "call_bid", "call_ask", "put_bid", "put_ask"):
            sub[c] = pd.to_numeric(sub[c], errors="coerce")

        sub = sub[sub["ticker"].isin(windows.keys())]
        if sub.empty:
            continue
        keep = np.zeros(len(sub), dtype=bool)
        for t, spans in windows.items():
            mt = (sub["ticker"] == t).values
            if not mt.any():
                continue
            dts = sub.loc[mt, "obs_date"]
            ok = np.zeros(mt.sum(), dtype=bool)
            for lo, hi in spans:
                ok |= ((dts >= lo) & (dts <= hi)).values
            keep[np.where(mt)[0]] = ok
        sub = sub[keep]
        if atm_band and not sub.empty:
            sub = sub[(sub["strike"] >= sub["spot"] * (1 - atm_band)) &
                      (sub["strike"] <= sub["spot"] * (1 + atm_band))]
        if not sub.empty:
            chunks.append(sub)
        if (i + 1) % 25 == 0:
            print("  ...%d/%d files, %d rows kept" %
                  (i + 1, len(files), sum(len(c) for c in chunks)))
    if not chunks:
        raise SystemExit("no rows survived ingestion -- check ticker overlap "
                         "between chains and events, and date formats")
    out = pd.concat(chunks, ignore_index=True)
    out["obs_date"] = out["obs_date"].dt.date
    out["expiry"] = out["expiry"].dt.date
    out = out.drop_duplicates(subset=["obs_date", "ticker", "expiry", "strike"])
    return out.sort_values(["ticker", "obs_date", "expiry", "strike"])


def run_ingest(raw: str, vendor: str, events_file: str, out_dir: str,
               colmap_file: str | None = None) -> None:
    os.makedirs(out_dir, exist_ok=True)
    events = load_events(events_file)
    print("events: %d rows, %d tickers (%s .. %s), session known for %.0f%%"
          % (len(events), events["ticker"].nunique(), events["ann_date"].min(),
             events["ann_date"].max(),
             100 * (events["session"] != "UNK").mean()))
    chains = ingest_chains(raw, vendor, events, colmap_file)
    print("chains: %d rows, %d tickers, %s .. %s"
          % (len(chains), chains["ticker"].nunique(),
             chains["obs_date"].min(), chains["obs_date"].max()))
    events.to_csv(os.path.join(out_dir, "events.csv"), index=False)
    chains.to_csv(os.path.join(out_dir, "chains.csv"), index=False)
    print("wrote canonical files -> %s" % out_dir)
