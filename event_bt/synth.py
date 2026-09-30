#!/usr/bin/env python
"""synth.py -- synthetic canonical dataset with PLANTED properties, used by
`bt.py selftest` to verify the whole pipeline before real vendor data arrives.

Planted world:
  * each name i has a true event-move scale m_i and ambient vol sig_i
  * at T-14 the implied move starts at m_i * exp(eps), eps ~ N(0, disp^2)
    (some events priced cheap, some rich, vs the name's own scale)
  * from T-14 to T-0 the log implied move REVERTS toward log(m_i) by fraction
    KAPPA (the repricing channel), plus small noise
  * the realized event move is drawn fairly from the FINAL implied move
    => unconditional long straddle ~ zero-EV gross; cheap-entry straddles
    positive gross (they harvest the repricing); costs subtract a known spread
  * quotes are Black-Scholes at additive total variance, bid/ask = mid -/+
    half of (w_frac * mid) per leg

So the engine must find: repricing slope < 0, unconditional ~ 0, cheap > rich.
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd

from engine import bs_price, C_ABS, DAYS

KAPPA = 0.6          # fraction of the log cheapness gap closed by T-0
DISP = 0.30          # dispersion of initial mispricing (log units)
W_FRAC = 0.05        # bid-ask width as fraction of each leg's mid
IM_NOISE = 0.03      # day-to-day log noise on the implied-move path
EVENT_VRP = 0.12     # realized event move drawn at (1-VRP) * final implied
                     # -> plants a known crush edge for the short side


def _next_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _fridays_after(d: date, n: int = 8):
    f = d + timedelta(days=(4 - d.weekday()) % 7)
    if f <= d:
        f += timedelta(days=7)
    return [f + timedelta(days=7 * k) for k in range(n)]


def generate(data_dir: str, n_tickers: int = 30, n_quarters: int = 22,
             seed: int = 11) -> dict:
    rng = np.random.default_rng(seed)
    os.makedirs(data_dir, exist_ok=True)
    tickers = ["SYN%02d" % i for i in range(n_tickers)]
    m_true = rng.uniform(0.03, 0.09, n_tickers)          # mean |event move|
    sig_amb = rng.uniform(0.22, 0.55, n_tickers)         # ambient vol
    s0 = rng.uniform(25, 400, n_tickers)

    ev_rows, ch_rows = [], []
    truth = {"kappa": KAPPA, "disp": DISP, "w_frac": W_FRAC,
             "per_event": []}

    for i, t in enumerate(tickers):
        anchor = date(2019, 1, 15) + timedelta(days=int(rng.integers(0, 60)))
        for q in range(n_quarters):
            ann = _next_weekday(anchor + timedelta(days=91 * q
                                                   + int(rng.integers(-4, 5))))
            session = "AMC" if rng.random() < 0.6 else "BMO"
            ev_rows.append({"ticker": t, "ann_date": ann.isoformat(),
                            "session": session})

            # event moment: after close of `ann` (AMC) or before open (BMO)
            im0 = m_true[i] * math.exp(rng.normal(0.0, DISP))
            gap0 = math.log(im0 / m_true[i])

            # trading days T-20 .. T+3
            days = []
            d = ann - timedelta(days=20)
            while d <= ann + timedelta(days=4):
                if d.weekday() < 5:
                    days.append(d)
                d += timedelta(days=1)
            exit_day = ann if session == "AMC" else max(
                dd for dd in days if dd < ann)
            capture = min(dd for dd in days if
                          (dd > ann if session == "AMC" else dd >= ann))

            # implied-move path (only meaningful before the event)
            im_path = {}
            for dd in days:
                if dd > exit_day:
                    break
                dte = (ann - dd).days
                progress = min(max((14.0 - dte) / 14.0, 0.0), 1.0)
                gap = gap0 * (1.0 - KAPPA * progress)
                im_path[dd] = m_true[i] * math.exp(
                    gap + rng.normal(0.0, IM_NOISE))
            im_final = im_path[exit_day]

            # spot path: ambient GBM per calendar day; event jump at capture
            sig_d = sig_amb[i] / math.sqrt(DAYS)
            spot = {}
            s = s0[i] * math.exp(rng.normal(0, 0.02))
            prev = days[0]
            evt_ret = math.copysign(1.0, rng.standard_normal()) * abs(
                rng.standard_normal()) * (im_final / C_ABS) * (1.0 - EVENT_VRP)
            for dd in days:
                ncal = max((dd - prev).days, 1) if dd != days[0] else 0
                if ncal:
                    s *= math.exp(-0.5 * sig_d ** 2 * ncal
                                  + sig_d * math.sqrt(ncal) * rng.standard_normal())
                if dd == capture:
                    s *= math.exp(evt_ret)
                spot[dd] = s
                prev = dd

            truth["per_event"].append({"ticker": t, "ann": ann.isoformat(),
                                       "im0": im0, "im_final": im_final,
                                       "m_true": m_true[i]})

            # chains: weekly Friday expiries within 50 DTE, 5 strikes
            for dd in days:
                exps = [e for e in _fridays_after(dd, 8)
                        if (e - dd).days <= 50]
                for e in exps:
                    dte = (e - dd).days
                    if dte < 1:
                        continue
                    # does expiry e (observed at dd) contain the event?
                    if session == "AMC":
                        has_evt = dd <= ann and e > ann
                    else:
                        has_evt = dd < ann and e >= ann
                    im_now = im_path.get(dd, im_final)
                    var_evt = (im_now / C_ABS) ** 2 if has_evt else 0.0
                    n_amb = dte - (1 if has_evt else 0)
                    tot = var_evt + sig_amb[i] ** 2 * n_amb / DAYS
                    iv = math.sqrt(tot / (dte / DAYS))
                    sp = spot[dd]
                    # fixed per-ticker grid so the entry strike exists on
                    # every later obs day even after the spot drifts; wide
                    # (+/-25%) so big-move paths -- the straddle's winners --
                    # are never dropped (that truncation biases E[P&L] down)
                    step = max(round(s0[i] * 0.025, 2), 0.5)
                    k0 = round(sp / step)
                    ks = [round((k0 + j) * step, 2) for j in range(-10, 11)]
                    for K in ks:
                        c = bs_price(sp, K, dte / DAYS, iv, "c")
                        p = bs_price(sp, K, dte / DAYS, iv, "p")
                        wc = max(W_FRAC * c, 0.02)
                        wp = max(W_FRAC * p, 0.02)
                        ch_rows.append({
                            "obs_date": dd.isoformat(), "ticker": t,
                            "expiry": e.isoformat(), "spot": round(sp, 4),
                            "strike": K,
                            "call_bid": round(max(c - wc / 2, 0.0), 4),
                            "call_ask": round(c + wc / 2, 4),
                            "put_bid": round(max(p - wp / 2, 0.0), 4),
                            "put_ask": round(p + wp / 2, 4),
                        })

    pd.DataFrame(ev_rows).to_csv(os.path.join(data_dir, "events.csv"), index=False)
    pd.DataFrame(ch_rows).to_csv(os.path.join(data_dir, "chains.csv"), index=False)
    with open(os.path.join(data_dir, "_truth.json"), "w") as fh:
        json.dump(truth, fh)
    return truth
