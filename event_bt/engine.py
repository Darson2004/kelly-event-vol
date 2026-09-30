#!/usr/bin/env python
"""engine.py -- event-vol backtest engine (pre-earnings straddle RV).

Core of the event_bt harness. Consumes CANONICAL data (see
DATA_SPEC.md) and runs three analyses:

  repricing  Does the implied earnings move rise from T-14 to T-0 when it
             starts cheap vs the name's own history? Pure measurement of the
             one channel that can make the long trade positive-EV (the
             unconditional T-14 -> T-0 straddle is zero-EV before costs;
             proof in scripts/verify_vv_math.py).
  replicate  Honest re-run of the Volatility Vibes video-#6 trade: long ATM
             straddle entered ~T-14, exited at the last close before the
             announcement. Unconditional baseline + fixed cheapness rule +
             expanding walk-forward linear model, all at REAL quoted spreads.
  rvbook     The two-sided book the channel never combined: long cheap event
             vol T-14 -> T-0 and short rich event vol T-0 -> T+1 (the crush),
             same signal, both directions, daily-marked portfolio curve.

Leakage rules: every per-name "history" feature uses strictly-prior events
only. Walk-forward fits only use trades whose EXIT precedes the fit date.

No scipy dependency; BS inversion is bisection. matplotlib optional.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

DAYS = 365.0
C_ABS = math.sqrt(2.0 / math.pi)


# ---------------------------------------------------------------------------
# Black-Scholes helpers (self-contained; bisection IV, no scipy)
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S: float, K: float, T: float, sigma: float, cp: str, r: float = 0.0) -> float:
    if T <= 0 or sigma <= 0:
        intr = S - K if cp == "c" else K - S
        return max(intr, 0.0)
    sqt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sqt
    d2 = d1 - sqt
    if cp == "c":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_delta(S: float, K: float, T: float, sigma: float, cp: str, r: float = 0.0) -> float:
    if T <= 0 or sigma <= 0:
        if cp == "c":
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1) if cp == "c" else _norm_cdf(d1) - 1.0


def straddle_iv(price: float, S: float, K: float, T: float, r: float = 0.0) -> float:
    """IV that reprices call+put at `strike` to `price`. Bisection; NaN outside bounds."""
    if price <= 0 or T <= 0 or S <= 0:
        return float("nan")
    intr = abs(S - K)
    if price <= intr + 1e-12:
        return float("nan")
    lo, hi = 1e-4, 10.0
    if bs_price(S, K, T, hi, "c", r) + bs_price(S, K, T, hi, "p", r) < price:
        return float("nan")
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, mid, "c", r) + bs_price(S, K, T, mid, "p", r) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def implied_vol(price: float, S: float, K: float, T: float, cp: str, r: float = 0.0) -> float:
    """Bisection IV. NaN if the price is outside no-arb bounds."""
    if price <= 0 or T <= 0 or S <= 0:
        return float("nan")
    intr = max((S - K) if cp == "c" else (K - S), 0.0)
    if price <= intr + 1e-12:
        return float("nan")
    lo, hi = 1e-4, 10.0
    if bs_price(S, K, T, hi, cp, r) < price:
        return float("nan")
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, mid, cp, r) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Canonical data loading
# ---------------------------------------------------------------------------

REQ_EVENT_COLS = ["ticker", "ann_date", "session"]
REQ_CHAIN_COLS = ["obs_date", "ticker", "expiry", "spot", "strike",
                  "call_bid", "call_ask", "put_bid", "put_ask"]


def load_canonical(data_dir: str):
    """Load events.csv + chains.csv (+ optional equity.csv) from data_dir."""
    ev_path = os.path.join(data_dir, "events.csv")
    ch_path = os.path.join(data_dir, "chains.csv")
    for p in (ev_path, ch_path):
        if not os.path.exists(p):
            raise SystemExit("missing canonical file: %s (see DATA_SPEC.md; "
                             "run `bt.py ingest` on vendor data first)" % p)
    events = pd.read_csv(ev_path)
    chains = pd.read_csv(ch_path)
    miss_e = [c for c in REQ_EVENT_COLS if c not in events.columns]
    miss_c = [c for c in REQ_CHAIN_COLS if c not in chains.columns]
    if miss_e:
        raise SystemExit("events.csv missing columns: %s" % miss_e)
    if miss_c:
        raise SystemExit("chains.csv missing columns: %s" % miss_c)

    events["ann_date"] = pd.to_datetime(events["ann_date"]).dt.date
    events["session"] = events["session"].fillna("AMC").str.upper().replace({"UNK": "AMC"})
    events["ticker"] = events["ticker"].str.upper()
    chains["obs_date"] = pd.to_datetime(chains["obs_date"]).dt.date
    chains["expiry"] = pd.to_datetime(chains["expiry"]).dt.date
    chains["ticker"] = chains["ticker"].str.upper()
    for c in ("spot", "strike", "call_bid", "call_ask", "put_bid", "put_ask"):
        chains[c] = pd.to_numeric(chains[c], errors="coerce")
    # optional vendor IV columns
    for c in ("call_iv", "put_iv"):
        if c not in chains.columns:
            chains[c] = np.nan
        else:
            chains[c] = pd.to_numeric(chains[c], errors="coerce")

    eq_path = os.path.join(data_dir, "equity.csv")
    equity = None
    if os.path.exists(eq_path):
        equity = pd.read_csv(eq_path)
        equity["date"] = pd.to_datetime(equity["date"]).dt.date
        equity["ticker"] = equity["ticker"].str.upper()

    events = events.drop_duplicates(subset=["ticker", "ann_date"]).reset_index(drop=True)
    return events, chains, equity


# ---------------------------------------------------------------------------
# Per-event assembly
# ---------------------------------------------------------------------------

@dataclass
class EventRec:
    ticker: str
    ann_date: date
    session: str
    entry_date: date | None = None
    exit_date: date | None = None
    capture_date: date | None = None
    expiry_post: date | None = None
    expiry_pre: date | None = None
    strike: float = float("nan")
    spot_entry: float = float("nan")
    spot_exit: float = float("nan")
    spot_capture: float = float("nan")
    realized_move: float = float("nan")
    # straddle quotes at fixed strike, post expiry: {date: (bid, ask)}
    marks: dict = field(default_factory=dict)
    # call-leg-only quotes at the same strike (half-spread structure)
    marks_call: dict = field(default_factory=dict)
    # pre-expiry straddle quotes at fixed strike (calendar short leg)
    marks_pre: dict = field(default_factory=dict)
    # implied-move path {date: im}; ambient iv path {date: iv}
    im_path: dict = field(default_factory=dict)
    amb_path: dict = field(default_factory=dict)
    # daily spot {date: close} over the hold window
    spots: dict = field(default_factory=dict)
    skip_reason: str = ""


def _straddle_quote(rows: pd.DataFrame, strike: float):
    """(bid, ask) of call+put at strike, NaN-safe. rows = one (tkr,d,exp) slice."""
    r = rows[np.isclose(rows["strike"], strike)]
    if r.empty:
        return float("nan"), float("nan")
    r = r.iloc[0]
    bid = r["call_bid"] + r["put_bid"]
    ask = r["call_ask"] + r["put_ask"]
    if bid < 0 or ask <= 0 or ask < bid:
        return float("nan"), float("nan")
    return float(bid), float(ask)


def _call_quote(rows: pd.DataFrame, strike: float):
    """(bid, ask) of the call alone at strike, NaN-safe."""
    r = rows[np.isclose(rows["strike"], strike)]
    if r.empty:
        return float("nan"), float("nan")
    r = r.iloc[0]
    if r["call_ask"] <= 0 or r["call_ask"] < r["call_bid"]:
        return float("nan"), float("nan")
    return float(max(r["call_bid"], 0.0)), float(r["call_ask"])


def _atm_iv(rows: pd.DataFrame, spot: float, dte: int, r: float = 0.0):
    """ATM IV at obs: vendor IV cols if present, else BS-invert call+put mids."""
    if rows.empty or dte < 1 or not (spot > 0):
        return float("nan")
    row = rows.iloc[(rows["strike"] - spot).abs().argsort().iloc[0]]
    T = max(dte, 0.5) / DAYS
    ivs = []
    for cp, ivcol, b, a in (("c", "call_iv", "call_bid", "call_ask"),
                            ("p", "put_iv", "put_bid", "put_ask")):
        v = row[ivcol]
        if not pd.isna(v) and 0.005 < v < 5.0:
            ivs.append(float(v))
            continue
        if pd.isna(row[b]) or pd.isna(row[a]) or row[a] <= 0:
            continue
        mid = 0.5 * (row[b] + row[a])
        iv = implied_vol(mid, spot, float(row["strike"]), T, cp, r)
        if not math.isnan(iv) and 0.005 < iv < 5.0:
            ivs.append(iv)
    return float(np.mean(ivs)) if ivs else float("nan")


def implied_move_at(day_slice: pd.DataFrame, spot: float, obs: date,
                    pre_ok: date, capture: date):
    """Back out (implied_move, iv_amb, iv_post, expiry_post, expiry_pre) at obs.

    day_slice = all chain rows for (ticker, obs). Variance additivity in
    calendar days, matching toolkit/event_vol.py and the VV videos.
    """
    expiries = sorted(day_slice["expiry"].unique())
    post = [e for e in expiries if e > pre_ok]
    pre = [e for e in expiries if e <= pre_ok and e > obs]
    if not post:
        return (float("nan"),) * 3 + (None, None)
    e_post = post[0]
    dte_post = (e_post - obs).days
    iv_post = _atm_iv(day_slice[day_slice["expiry"] == e_post], spot, dte_post)
    if math.isnan(iv_post):
        return (float("nan"),) * 3 + (e_post, None)

    e_pre, iv_amb = None, float("nan")
    if pre:
        e_pre = pre[-1]
        iv_amb = _atm_iv(day_slice[day_slice["expiry"] == e_pre], spot,
                         (e_pre - obs).days)
    if math.isnan(iv_amb) and len(post) >= 2:
        e2 = post[1]
        dte2 = (e2 - obs).days
        iv2 = _atm_iv(day_slice[day_slice["expiry"] == e2], spot, dte2)
        if not math.isnan(iv2) and dte2 > dte_post:
            fwd = (iv2 ** 2 * dte2 - iv_post ** 2 * dte_post) / (dte2 - dte_post)
            iv_amb = math.sqrt(max(fwd, 1e-6))
    if math.isnan(iv_amb):
        return float("nan"), float("nan"), iv_post, e_post, e_pre

    var_tot = iv_post ** 2 * dte_post / DAYS
    var_amb = iv_amb ** 2 * max(dte_post - 1, 0) / DAYS
    var_evt = var_tot - var_amb
    im = C_ABS * math.sqrt(var_evt) if var_evt > 0 else float("nan")
    return im, iv_amb, iv_post, e_post, e_pre


def build_event_records(events: pd.DataFrame, chains: pd.DataFrame,
                        entry_target: int = 14, entry_window: int = 4,
                        post_expiry_mode: str = "first") -> list[EventRec]:
    """Assemble one EventRec per (ticker, earnings event)."""
    recs = []
    chains = chains.sort_values(["ticker", "obs_date", "expiry", "strike"])
    by_tkr = {t: g for t, g in chains.groupby("ticker")}

    for _, ev in events.iterrows():
        rec = EventRec(ev["ticker"], ev["ann_date"], ev["session"])
        g = by_tkr.get(ev["ticker"])
        if g is None:
            rec.skip_reason = "no chain data for ticker"
            recs.append(rec)
            continue
        ann = ev["ann_date"]
        obs_dates = sorted(g["obs_date"].unique())
        # expiry counts as pre-event if it stops trading before the release
        pre_ok = ann if ev["session"] == "AMC" else ann - timedelta(days=1)
        # exit = last close strictly before the release
        exits = [d for d in obs_dates if (d <= ann if ev["session"] == "AMC"
                                          else d < ann)]
        if not exits:
            rec.skip_reason = "no obs on/near exit day"
            recs.append(rec)
            continue
        rec.exit_date = exits[-1]
        if (ann - rec.exit_date).days > 3:
            rec.skip_reason = "exit-day data too far from announcement"
            recs.append(rec)
            continue
        # capture close: first close that includes the event return
        if ev["session"] == "BMO":
            caps = [d for d in obs_dates if d >= ann]
        else:
            caps = [d for d in obs_dates if d > ann]
        rec.capture_date = caps[0] if caps else None

        # entry: obs closest to T-entry_target within +/- entry_window
        lo = ann - timedelta(days=entry_target + entry_window)
        hi = ann - timedelta(days=max(entry_target - entry_window, 2))
        cand = [d for d in obs_dates if lo <= d <= hi]
        if not cand:
            rec.skip_reason = "no obs in entry window"
            recs.append(rec)
            continue
        tgt = ann - timedelta(days=entry_target)
        rec.entry_date = min(cand, key=lambda d: abs((d - tgt).days))

        day_e = g[g["obs_date"] == rec.entry_date]
        spot_e = float(day_e["spot"].iloc[0])
        rec.spot_entry = spot_e
        im, amb, ivp, e_post, e_pre = implied_move_at(day_e, spot_e,
                                                      rec.entry_date, pre_ok,
                                                      rec.capture_date or ann)
        if e_post is None:
            rec.skip_reason = "no post-event expiry at entry"
            recs.append(rec)
            continue
        if post_expiry_mode == "monthly":
            months = [e for e in sorted(day_e["expiry"].unique())
                      if e > pre_ok and 15 <= e.day <= 21 and e.weekday() == 4]
            if months:
                e_post = months[0]
        rec.expiry_post, rec.expiry_pre = e_post, e_pre

        # ATM strike fixed at entry
        rows_e = day_e[day_e["expiry"] == e_post]
        if rows_e.empty:
            rec.skip_reason = "no rows for post expiry at entry"
            recs.append(rec)
            continue
        rec.strike = float(rows_e.iloc[(rows_e["strike"] - spot_e).abs()
                                       .argsort().iloc[0]]["strike"])

        # walk entry..capture: marks + implied-move path
        span = [d for d in obs_dates if rec.entry_date <= d <=
                (rec.capture_date or rec.exit_date)]
        for d in span:
            day = g[g["obs_date"] == d]
            spot_d = float(day["spot"].iloc[0])
            rec.spots[d] = spot_d
            post_rows = day[day["expiry"] == e_post]
            bid, ask = _straddle_quote(post_rows, rec.strike)
            if not math.isnan(ask):
                rec.marks[d] = (bid, ask)
            cb, ca = _call_quote(post_rows, rec.strike)
            if not math.isnan(ca):
                rec.marks_call[d] = (cb, ca)
            if e_pre is not None and d <= rec.exit_date and e_pre >= d:
                b2, a2 = _straddle_quote(day[day["expiry"] == e_pre], rec.strike)
                if not math.isnan(a2):
                    rec.marks_pre[d] = (b2, a2)
            if d <= rec.exit_date:
                im_d, amb_d, _, _, _ = implied_move_at(day, spot_d, d, pre_ok,
                                                       rec.capture_date or ann)
                if not math.isnan(im_d):
                    rec.im_path[d] = im_d
                if not math.isnan(amb_d):
                    rec.amb_path[d] = amb_d
            if d == rec.exit_date:
                rec.spot_exit = spot_d
            if rec.capture_date and d == rec.capture_date:
                rec.spot_capture = spot_d

        if rec.entry_date not in rec.marks or rec.exit_date not in rec.marks:
            rec.skip_reason = "missing straddle quote at entry or exit"
        elif rec.spot_capture > 0 and rec.spot_exit > 0:
            rec.realized_move = abs(rec.spot_capture / rec.spot_exit - 1.0)
        recs.append(rec)
    return recs


# ---------------------------------------------------------------------------
# Signals (leak-free) + trade table
# ---------------------------------------------------------------------------

def fill_px(bid: float, ask: float, side: str, phi: float) -> float:
    """Execution price: mid +/- phi * half-spread. side='buy'|'sell'."""
    mid = 0.5 * (bid + ask)
    half = 0.5 * (ask - bid)
    return mid + phi * half if side == "buy" else mid - phi * half


def build_trade_table(recs: list[EventRec], phi: float = 0.5,
                      commission: float = 0.75, min_priors: int = 2) -> pd.DataFrame:
    """One row per usable event with signals and long/short straddle P&L.

    Signals use strictly-prior events of the same name only.
    Costs: phi = fraction of half-spread paid per leg side;
    commission = $ per contract per side (4 sides round-trip on a straddle).
    """
    rows = []
    hist_im: dict[str, list] = {}     # ticker -> [(ann_date, im_entry)]
    hist_rm: dict[str, list] = {}     # ticker -> [(ann_date, realized_move)]

    for rec in sorted(recs, key=lambda r: (r.ann_date, r.ticker)):
        t = rec.ticker
        pri_im = [v for (a, v) in hist_im.get(t, []) if a < rec.ann_date]
        pri_rm = [v for (a, v) in hist_rm.get(t, []) if a < rec.ann_date]
        im_e = rec.im_path.get(rec.entry_date, float("nan")) if rec.entry_date else float("nan")
        if not math.isnan(rec.realized_move):
            hist_rm.setdefault(t, []).append((rec.ann_date, rec.realized_move))
        if not math.isnan(im_e):
            hist_im.setdefault(t, []).append((rec.ann_date, im_e))
        if rec.skip_reason:
            continue

        im_x = rec.im_path.get(rec.exit_date, float("nan"))
        eb, ea = rec.marks[rec.entry_date]
        xb, xa = rec.marks[rec.exit_date]
        entry_mid, exit_mid = 0.5 * (eb + ea), 0.5 * (xb + xa)
        if entry_mid <= 0 or exit_mid <= 0:
            continue
        # long leg: buy at entry (ask side), sell at exit (bid side)
        buy_in = fill_px(eb, ea, "buy", phi)
        sell_out = fill_px(xb, xa, "sell", phi)
        comm_frac = 4 * commission / (100.0 * entry_mid)
        ret_gross = exit_mid / entry_mid - 1.0
        ret_net = sell_out / buy_in - 1.0 - comm_frac

        # delta-hedged variant (GXZ-style vol P&L isolation): rebalance the
        # spot hedge at each close, delta from the straddle-implied vol
        ds = sorted(d for d in rec.marks
                    if rec.entry_date <= d <= rec.exit_date and d in rec.spots)
        hedge, hedge_c, ok_dh = 0.0, 0.0, len(ds) >= 2
        if ok_dh:
            for d0, d1 in zip(ds[:-1], ds[1:]):
                b0, a0 = rec.marks[d0]
                sp0, sp1 = rec.spots[d0], rec.spots[d1]
                T0 = max((rec.expiry_post - d0).days, 1) / DAYS
                siv = straddle_iv(0.5 * (b0 + a0), sp0, rec.strike, T0)
                if math.isnan(siv):
                    ok_dh = False
                    break
                dc = bs_delta(sp0, rec.strike, T0, siv, "c")
                hedge -= (dc + bs_delta(sp0, rec.strike, T0, siv, "p")) \
                    * (sp1 - sp0)
                hedge_c -= dc * (sp1 - sp0)
        dh_gross = ((exit_mid - entry_mid + hedge) / entry_mid
                    if ok_dh else float("nan"))
        dh_net = ((sell_out - buy_in + hedge) / buy_in - comm_frac
                  if ok_dh else float("nan"))

        # half-spread structure: delta-hedged SINGLE call at the same strike.
        # Same vol bet, 2 option legs round-trip instead of 4 -> half the toll
        # (the stock hedge trades at equity spreads, ~free by comparison).
        leg_gross = leg_net = float("nan")
        if (ok_dh and rec.entry_date in rec.marks_call
                and rec.exit_date in rec.marks_call):
            ceb, cea = rec.marks_call[rec.entry_date]
            cxb, cxa = rec.marks_call[rec.exit_date]
            c_in_mid, c_out_mid = 0.5 * (ceb + cea), 0.5 * (cxb + cxa)
            if c_in_mid > 0:
                c_buy = fill_px(ceb, cea, "buy", phi)
                c_sell = fill_px(cxb, cxa, "sell", phi)
                c_comm = 2 * commission / (100.0 * c_in_mid)
                leg_gross = (c_out_mid - c_in_mid + hedge_c) / c_in_mid
                leg_net = (c_sell - c_buy + hedge_c) / c_buy - c_comm

        # short leg (crush): sell at exit-day close, buy back at capture close
        s_ret_gross = s_ret_net = float("nan")
        if rec.capture_date and rec.capture_date in rec.marks:
            cb, ca = rec.marks[rec.capture_date]
            if cb >= 0 and ca > 0:
                sh_in = fill_px(xb, xa, "sell", phi)
                sh_out = fill_px(cb, ca, "buy", phi)
                s_ret_gross = (exit_mid - 0.5 * (cb + ca)) / exit_mid
                s_ret_net = (sh_in - sh_out) / exit_mid - 4 * commission / (100.0 * exit_mid)

        # ambient realized vol over the hold (annualized close-to-close)
        sp_days = sorted(d for d in rec.spots
                         if rec.entry_date <= d <= rec.exit_date)
        amb_rv = float("nan")
        if len(sp_days) >= 6:
            lr = np.diff(np.log([rec.spots[d] for d in sp_days]))
            ncal = (sp_days[-1] - sp_days[0]).days
            if ncal > 0:
                amb_rv = float(np.sqrt(np.sum(lr ** 2) * DAYS / ncal))

        rows.append({
            "ticker": t, "ann_date": rec.ann_date, "session": rec.session,
            "entry_date": rec.entry_date, "exit_date": rec.exit_date,
            "capture_date": rec.capture_date, "expiry_post": rec.expiry_post,
            "strike": rec.strike, "spot_entry": rec.spot_entry,
            "dte_entry": (rec.ann_date - rec.entry_date).days,
            "im_entry": im_e, "im_exit": im_x,
            "d_log_im": (math.log(im_x / im_e)
                         if im_e > 0 and im_x > 0 else float("nan")),
            "iv_amb_entry": rec.amb_path.get(rec.entry_date, float("nan")),
            "realized_move": rec.realized_move,
            "prem_frac_entry": entry_mid / rec.spot_entry,
            "spread_frac_entry": (ea - eb) / entry_mid,
            "spread_frac_exit": (xa - xb) / exit_mid,
            "n_prior_im": len(pri_im), "n_prior_rm": len(pri_rm),
            "ratio_avg_im": (im_e / np.mean(pri_im)
                             if len(pri_im) >= min_priors and np.mean(pri_im) > 0
                             else float("nan")),
            "ratio_last_im": (im_e / pri_im[-1]
                              if pri_im and pri_im[-1] > 0 else float("nan")),
            "ratio_avg_rm": (im_e / np.mean(pri_rm)
                             if len(pri_rm) >= min_priors and np.mean(pri_rm) > 0
                             else float("nan")),
            "ratio_last_rm": (im_e / pri_rm[-1]
                              if pri_rm and pri_rm[-1] > 0 else float("nan")),
            "long_ret_gross": ret_gross, "long_ret_net": ret_net,
            "long_ret_gross_dh": dh_gross, "long_ret_net_dh": dh_net,
            "leg_ret_gross_dh": leg_gross, "leg_ret_net_dh": leg_net,
            "short_ret_gross": s_ret_gross, "short_ret_net": s_ret_net,
            "amb_rv_hold": amb_rv,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["entry_date", "ticker"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Analysis 1: the repricing channel
# ---------------------------------------------------------------------------

def analysis_repricing(df: pd.DataFrame, outdir: str) -> dict:
    """Does entry cheapness predict implied-move repricing into the event?

    Works with or without trade P&L columns -- a cores-only dataset (ORATS
    impliedEarningsMove history, no chains) still answers the channel question.
    """
    d = df.dropna(subset=["d_log_im", "ratio_avg_im"]).copy()
    out = {"n": int(len(d))}
    if len(d) < 30:
        out["note"] = "insufficient events with implied-move history (n=%d)" % len(d)
        return out

    d["bucket"] = pd.qcut(d["ratio_avg_im"], 5, labels=False, duplicates="drop")
    aggs = dict(n=("d_log_im", "size"),
                ratio_avg_im=("ratio_avg_im", "mean"),
                mean_repricing=("d_log_im", "mean"),
                med_repricing=("d_log_im", "median"))
    if "long_ret_gross" in d.columns:
        aggs.update(mean_long_gross=("long_ret_gross", "mean"),
                    mean_long_net=("long_ret_net", "mean"),
                    win_long_net=("long_ret_net",
                                  lambda s: float((s > 0).mean())))
    tab = d.groupby("bucket").agg(**aggs).reset_index()
    tab.to_csv(os.path.join(outdir, "repricing_by_cheapness.csv"), index=False)

    # OLS d_log_im ~ log(ratio_avg_im); mean reversion => negative slope
    x = np.log(d["ratio_avg_im"].values)
    y = d["d_log_im"].values
    X = np.column_stack([np.ones_like(x), x])
    beta, res, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    se = math.sqrt(resid.var(ddof=2) / max(((x - x.mean()) ** 2).sum(), 1e-12))
    out.update({
        "slope": float(beta[1]), "slope_t": float(beta[1] / se) if se > 0 else float("nan"),
        "intercept": float(beta[0]),
        "mean_repricing_all": float(y.mean()),
        "mean_repricing_cheapest_q": float(tab["mean_repricing"].iloc[0]),
        "mean_repricing_richest_q": float(tab["mean_repricing"].iloc[-1]),
        "table": tab.to_dict("records"),
    })

    # per-year slope stability
    d["year"] = pd.to_datetime(d["ann_date"].astype(str)).dt.year
    yr = []
    for yv, g in d.groupby("year"):
        if len(g) < 20:
            continue
        xg = np.log(g["ratio_avg_im"].values)
        Xg = np.column_stack([np.ones_like(xg), xg])
        bg, *_ = np.linalg.lstsq(Xg, g["d_log_im"].values, rcond=None)
        yr.append({"year": int(yv), "n": len(g), "slope": float(bg[1]),
                   "mean_repricing": float(g["d_log_im"].mean())})
    pd.DataFrame(yr).to_csv(os.path.join(outdir, "repricing_by_year.csv"), index=False)
    out["by_year"] = yr
    return out


def build_cores_table(cores: pd.DataFrame, events: pd.DataFrame,
                      entry_target: int = 14, entry_window: int = 4,
                      min_priors: int = 2) -> pd.DataFrame:
    """Event table from a vendor implied-earnings-move history alone
    (e.g. ORATS hist/cores impliedEarningsMove) -- no chains needed.
    Powers the repricing analysis only. cores columns: obs_date, ticker, im.
    """
    cores = cores.dropna(subset=["im"])
    cores = cores[cores["im"] > 0]
    by_tkr = {t: g.sort_values("obs_date") for t, g in cores.groupby("ticker")}
    rows, hist_im = [], {}
    for _, ev in events.sort_values(["ann_date", "ticker"]).iterrows():
        t, ann = ev["ticker"], ev["ann_date"]
        g = by_tkr.get(t)
        if g is None:
            continue
        obs = list(g["obs_date"])
        ims = dict(zip(g["obs_date"], g["im"]))
        exits = [d for d in obs if (d <= ann if ev["session"] == "AMC"
                                    else d < ann)]
        lo = ann - timedelta(days=entry_target + entry_window)
        hi = ann - timedelta(days=max(entry_target - entry_window, 2))
        cand = [d for d in obs if lo <= d <= hi]
        if not exits or not cand or (ann - exits[-1]).days > 3:
            continue
        tgt = ann - timedelta(days=entry_target)
        entry = min(cand, key=lambda d: abs((d - tgt).days))
        im_e, im_x = ims[entry], ims[exits[-1]]
        pri = [v for (a, v) in hist_im.get(t, []) if a < ann]
        hist_im.setdefault(t, []).append((ann, im_e))
        rows.append({
            "ticker": t, "ann_date": ann, "entry_date": entry,
            "exit_date": exits[-1], "im_entry": im_e, "im_exit": im_x,
            "d_log_im": math.log(im_x / im_e),
            "n_prior_im": len(pri),
            "ratio_avg_im": (im_e / np.mean(pri)
                             if len(pri) >= min_priors else float("nan")),
            "ratio_last_im": im_e / pri[-1] if pri else float("nan"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Analysis 2: replicate the VV trade honestly
# ---------------------------------------------------------------------------

FEATURES = ["ratio_avg_im", "ratio_last_im", "ratio_avg_rm", "ratio_last_rm"]


def kelly_fraction(rets, f_max: float = 2.0) -> tuple[float, float]:
    """Kelly-optimal premium fraction f* = argmax E[log(1+f*r)] over the
    empirical per-trade return distribution, and the growth rate at f*.
    f*=0 is the Kelly veto (kelly.py doctrine: trade at 0.25-0.5x f*)."""
    r = pd.Series(rets).dropna().values
    if len(r) < 30:
        return float("nan"), float("nan")
    best_f, best_g = 0.0, 0.0
    for f in np.linspace(0.0, f_max, 401):
        w = 1.0 + f * r
        if w.min() <= 1e-9:
            break
        g = float(np.mean(np.log(w)))
        if g > best_g:
            best_f, best_g = float(f), g
    return best_f, best_g


def _stats(s: pd.Series) -> dict:
    s = s.dropna()
    if s.empty:
        return {"n": 0}
    kf, kg = kelly_fraction(s)
    return {"n": int(len(s)), "mean": float(s.mean()), "median": float(s.median()),
            "win": float((s > 0).mean()), "std": float(s.std()),
            "t": float(s.mean() / s.std() * math.sqrt(len(s))) if s.std() > 0 else float("nan"),
            "p5": float(s.quantile(0.05)), "p95": float(s.quantile(0.95)),
            "top_decile_share": _top_decile_share(s),
            "kelly_f": kf, "kelly_g": kg}


def _top_decile_share(s: pd.Series) -> float:
    """Fraction of total positive P&L delivered by the best 10% of trades."""
    s = s.dropna()
    if len(s) < 10 or s.sum() == 0:
        return float("nan")
    k = max(int(0.1 * len(s)), 1)
    top = s.nlargest(k).sum()
    return float(top / s.abs().sum())


def walkforward_ols(df: pd.DataFrame, target: str = "long_ret_net",
                    burn_years: int = 3, block_months: int = 24) -> pd.DataFrame:
    """Expanding-window OLS; returns df with 'pred' for OOS rows only.

    Fit set = trades whose EXIT precedes the block start (no overlap leakage).
    """
    d = df.dropna(subset=FEATURES + [target]).copy()
    if d.empty:
        return d.assign(pred=np.nan)
    d["entry_ts"] = pd.to_datetime(d["entry_date"].astype(str))
    d["exit_ts"] = pd.to_datetime(d["exit_date"].astype(str))
    start = d["entry_ts"].min() + pd.DateOffset(years=burn_years)
    d["pred"] = np.nan
    t0 = start
    while t0 <= d["entry_ts"].max():
        t1 = t0 + pd.DateOffset(months=block_months)
        fit = d[d["exit_ts"] < t0]
        blk = (d["entry_ts"] >= t0) & (d["entry_ts"] < t1)
        if len(fit) >= 60 and blk.any():
            X = np.log(fit[FEATURES].values.clip(1e-3, 1e3))
            X = np.column_stack([np.ones(len(X)), X])
            y = fit[target].values
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            Xb = np.log(d.loc[blk, FEATURES].values.clip(1e-3, 1e3))
            Xb = np.column_stack([np.ones(len(Xb)), Xb])
            d.loc[blk, "pred"] = Xb @ beta
        t0 = t1
    return d


def analysis_replicate(df: pd.DataFrame, outdir: str,
                       rule_avg: float = 0.90, rule_last: float = 1.10) -> dict:
    out = {}
    out["unconditional_gross"] = _stats(df["long_ret_gross"])
    out["unconditional_net"] = _stats(df["long_ret_net"])
    out["unconditional_dh_net"] = _stats(df["long_ret_net_dh"])

    # fixed cheapness rule (event_vol.py's placeholder screen)
    m = (df["ratio_avg_im"] <= rule_avg) & (
        df["ratio_last_im"].isna() | (df["ratio_last_im"] <= rule_last))
    out["fixed_rule"] = {"rule": "ratio_avg_im<=%.2f & ratio_last_im<=%.2f"
                                 % (rule_avg, rule_last),
                         "gross": _stats(df.loc[m, "long_ret_gross"]),
                         "net": _stats(df.loc[m, "long_ret_net"]),
                         "dh_net": _stats(df.loc[m, "long_ret_net_dh"]),
                         "leg_dh_net": _stats(df.loc[m, "leg_ret_net_dh"])}
    # same rule on realized-move history (works with zero implied history)
    m2 = (df["ratio_avg_rm"] <= rule_avg)
    out["fixed_rule_rm"] = {"rule": "ratio_avg_rm<=%.2f" % rule_avg,
                            "gross": _stats(df.loc[m2, "long_ret_gross"]),
                            "net": _stats(df.loc[m2, "long_ret_net"])}

    wf = walkforward_ols(df)
    oos = wf.dropna(subset=["pred"])
    sel = oos[oos["pred"] > 0]
    out["walkforward"] = {"n_oos": int(len(oos)), "n_selected": int(len(sel)),
                          "gross": _stats(sel["long_ret_gross"]),
                          "net": _stats(sel["long_ret_net"])}
    if not sel.empty:
        sel = sel.copy()
        sel["year"] = pd.to_datetime(sel["entry_date"].astype(str)).dt.year
        py = sel.groupby("year")["long_ret_net"].agg(["size", "mean", "median"])
        py["win"] = sel.groupby("year")["long_ret_net"].apply(lambda s: (s > 0).mean())
        py.to_csv(os.path.join(outdir, "replicate_wf_by_year.csv"))
        out["walkforward"]["by_year"] = py.reset_index().to_dict("records")
    wf.to_csv(os.path.join(outdir, "replicate_trades.csv"), index=False)
    return out


# ---------------------------------------------------------------------------
# Analysis 3: the RV book (long cheap T-14->T-0, short rich T-0->T+1)
# ---------------------------------------------------------------------------

def analysis_rvbook(df: pd.DataFrame, outdir: str, f: float = 0.02,
                    cheap: float = 0.90, rich: float = 1.15) -> dict:
    d = df.copy()
    d["leg"] = np.where(d["ratio_avg_im"] <= cheap, "long",
                        np.where(d["ratio_avg_im"] >= rich, "short", "none"))
    d.loc[d["ratio_avg_im"].isna(), "leg"] = "none"
    d["book_ret_net"] = np.where(d["leg"] == "long", d["long_ret_net"],
                                 np.where(d["leg"] == "short", d["short_ret_net"],
                                          np.nan))
    longs = d[d["leg"] == "long"]
    shorts = d[d["leg"] == "short"].dropna(subset=["short_ret_net"])
    out = {"long": {"gross": _stats(longs["long_ret_gross"]),
                    "net": _stats(longs["long_ret_net"])},
           "short": {"gross": _stats(shorts["short_ret_gross"]),
                     "net": _stats(shorts["short_ret_net"])}}

    # sequential equity curve at f per trade (ordered by exit of each leg)
    trades = []
    for _, r in longs.iterrows():
        if not pd.isna(r["long_ret_net"]):
            trades.append((r["exit_date"], r["long_ret_net"]))
    for _, r in shorts.iterrows():
        trades.append((r["capture_date"], r["short_ret_net"]))
    trades.sort(key=lambda x: str(x[0]))
    eq, curve = 1.0, []
    peak, maxdd = 1.0, 0.0
    for dt_, r in trades:
        eq *= (1.0 + f * r)
        peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1.0)
        curve.append({"date": dt_, "equity": eq})
    pd.DataFrame(curve).to_csv(os.path.join(outdir, "rvbook_equity.csv"), index=False)
    if curve:
        yrs = max((pd.to_datetime(str(trades[-1][0])) -
                   pd.to_datetime(str(trades[0][0]))).days / 365.25, 1e-6)
        rets = np.array([f * r for _, r in trades])
        out["book"] = {"n_trades": len(trades), "f": f,
                       "final_equity": eq, "cagr": eq ** (1 / yrs) - 1,
                       "max_dd": maxdd,
                       "sharpe_like": float(rets.mean() / rets.std()
                                            * math.sqrt(len(rets) / yrs))
                       if rets.std() > 0 else float("nan")}
    d.to_csv(os.path.join(outdir, "rvbook_trades.csv"), index=False)
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_all(data_dir: str, outdir: str, phi: float = 0.5,
            commission: float = 0.75, entry_target: int = 14,
            which: str = "all") -> dict:
    os.makedirs(outdir, exist_ok=True)
    events, chains, _equity = load_canonical(data_dir)
    recs = build_event_records(events, chains, entry_target=entry_target)
    usable = [r for r in recs if not r.skip_reason]
    skips = pd.Series([r.skip_reason for r in recs if r.skip_reason])
    df = build_trade_table(usable, phi=phi, commission=commission)

    summary = {
        "config": {"phi": phi, "commission": commission,
                   "entry_target": entry_target, "data_dir": data_dir},
        "n_events": int(len(events)), "n_usable": int(len(df)),
        "skip_reasons": skips.value_counts().to_dict() if len(skips) else {},
        "coverage": {
            "tickers": int(df["ticker"].nunique()) if len(df) else 0,
            "first": str(df["ann_date"].min()) if len(df) else None,
            "last": str(df["ann_date"].max()) if len(df) else None,
            "with_im_history": int(df["ratio_avg_im"].notna().sum()) if len(df) else 0,
            "median_spread_frac": float(df["spread_frac_entry"].median()) if len(df) else None,
        },
    }
    if len(df) == 0:
        summary["error"] = "no usable events -- run `bt.py validate` for details"
        return summary

    df.to_csv(os.path.join(outdir, "trades.csv"), index=False)
    if which in ("all", "repricing"):
        summary["repricing"] = analysis_repricing(df, outdir)
    if which in ("all", "replicate"):
        summary["replicate"] = analysis_replicate(df, outdir)
    if which in ("all", "rvbook"):
        summary["rvbook"] = analysis_rvbook(df, outdir)

    with open(os.path.join(outdir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    _maybe_plot(df, outdir)
    return summary


def _maybe_plot(df: pd.DataFrame, outdir: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    d = df.dropna(subset=["d_log_im", "ratio_avg_im"])
    if len(d) >= 30:
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(np.log(d["ratio_avg_im"]), d["d_log_im"], s=8, alpha=0.4)
        ax.axhline(0, lw=0.5, color="k")
        ax.axvline(0, lw=0.5, color="k")
        ax.set_xlabel("log(implied move / own history) at entry")
        ax.set_ylabel("log repricing of implied move, entry -> T-0")
        ax.set_title("Event-vol repricing vs entry cheapness")
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "repricing_scatter.png"), dpi=120)
        plt.close(fig)
