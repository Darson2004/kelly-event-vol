#!/usr/bin/env python
"""exec_harness.py -- FROZEN evaluator for EXECUTION research.

Sibling of explore/eval_harness.py, but the dependent variable is a COST, not
a P&L. Execution questions are "what did it cost us to get in, and when/whether
should we have gotten in at all" -- graded on cost and on paired policy
counterfactuals, never on net return (net = signal + cost, and grading a cost
feature on net return is circular; that mistake produced the FRAGILE H11
verdict in the signal pack on 2026-09-01).

Three things this harness does that the signal harness does not:

  1. COLUMN SEMANTICS ARE ASSERTED, NOT ASSUMED (`dict` command). Every panel
     column carries a machine-checked identity. The signal pack lost a probe
     cycle to `dte_entry`, which was named days-to-expiry and was actually
     (ann_date - entry_date). Here a column that fails its assertion cannot be
     graded at all.
  2. PAIRED COUNTERFACTUALS ARE FIRST-CLASS (`policy` command). Unlike a
     signal, an execution choice has an observable alternative: the SAME event
     entered on a different day. Within-event pairing removes event, name,
     regime and season confounding by construction -- the confounds that made
     every cross-sectional finding in the signal pack fragile.
  3. SCREENS ARE GRADED ON BOTH SIDES (`admit` command). A rule that skips
     trades must report what it gave up, not just what it saved. Refusing to
     trade wide markets is only an improvement if the foregone gross is
     smaller than the saved cost -- and in this project we already know
     high-spread names carry ~3x the gross tail rate.

Commands
--------
build   --chains F --events F --out F      assemble the execution panel
dict    --data F [--col C]                 verify column semantics; REFUSES on failure
test    --data F --feature COL --target cost_ic|stale|spread [--hyp ID --sign +|-]
policy  --data F --a LEAD --b LEAD [--metric cost|gross|net] [--hyp ID]
admit   --data F --screen "COL<=VAL" [--lead N] [--hyp ID]
selftest                                   planted-effect / planted-null checks

Every graded command APPENDS to experiments.jsonl BEFORE printing a result.
Alpha budget for the continual loop is tracked in STATE.json, not here.

Run: C:/Users/darso/AppData/Local/Programs/Python/Python312/python.exe exec_harness.py ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "experiments.jsonl")
MANIFEST = os.path.join(HERE, "SHA256SUMS")

LEADS = [3, 5, 7, 10, 14, 21]     # candidate entry leads, calendar days
N_BOOT = 4000
N_PERM = 2000
SEED = 20260901
PHI_DEFAULT = 0.5                 # half-spread paid, matches bt.py convention


# ---------------------------------------------------------------------------
# governance
# ---------------------------------------------------------------------------

def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest(path: str, require: bool = True) -> None:
    """Refuse to grade a panel that isn't in the frozen manifest."""
    if not os.path.exists(MANIFEST):
        if require:
            raise SystemExit("REFUSED: no SHA256SUMS manifest -- run `build` "
                             "then freeze the panel before grading")
        return
    want = {}
    for line in open(MANIFEST):
        if line.strip():
            h, _, name = line.strip().partition("  ")
            want[name] = h
    name = os.path.basename(path)
    if name not in want:
        raise SystemExit("REFUSED: %s is not in the frozen manifest" % name)
    if sha256(path) != want[name]:
        raise SystemExit("REFUSED: %s hash mismatch vs freeze -- panel changed"
                         % name)
    if "holdout" in name and os.environ.get("EXEC_HOLDOUT_OPEN") != "1":
        raise SystemExit("REFUSED: holdout panel is sealed (requires the "
                         "EXEC_HOLDOUT_OPEN=1 gate)")


# ---------------------------------------------------------------------------
# column semantics -- the H12 vaccine
# ---------------------------------------------------------------------------
# Each entry: (human meaning, assertion function over the dataframe).
# An assertion returning False means the column does NOT mean what it says,
# and every graded command refuses to run on it.

SEMANTICS = {
    "lead": ("calendar days from entry_date to ann_date",
             lambda d: ((pd.to_datetime(d["ann_date"]) -
                         pd.to_datetime(d["entry_date"])).dt.days
                        == d["lead"]).mean() > 0.999),
    "dte_true": ("calendar days from entry_date to option expiry",
                 lambda d: ((pd.to_datetime(d["expiry"]) -
                             pd.to_datetime(d["entry_date"])).dt.days
                            == d["dte_true"]).mean() > 0.999),
    "cost_frac": ("ONE-WAY half-spread as a fraction of straddle mid, i.e. "
                  "spread/(2*mid) -- the cost of crossing from mid to the "
                  "touch on a single side; in [0,1]",
                  lambda d: (d["cost_frac"].dropna().between(0, 1).mean() > 0.99)),
    "entry_mid": ("straddle mid at entry, strictly positive",
                  lambda d: (d["entry_mid"].dropna() > 0).mean() > 0.999),
    "gross_ret": ("(exit_mid-entry_mid)/entry_mid, mid-to-mid, pre-print exit",
                  lambda d: np.allclose(
                      d["gross_ret"].dropna(),
                      ((d["exit_mid"] - d["entry_mid"]) / d["entry_mid"]
                       ).loc[d["gross_ret"].dropna().index], atol=1e-6)),
    "stale_legs": ("count in {0..4} of the straddle's four quote legs "
                   "(call bid/ask, put bid/ask) identical to the previous "
                   "session's quote for the same strike",
                   lambda d: (d["stale_legs"].dropna().isin([0, 1, 2, 3, 4])
                              .mean() > 0.999)),
    "stale_econ": ("1 if the straddle MID is unchanged from the previous "
                   "session while the underlying spot moved >=0.5% -- an "
                   "economically impossible quote, i.e. a stale mark",
                   lambda d: set(d["stale_econ"].dropna().unique()) <= {0, 1}),
    "book_bad": ("1 if the entry book is defective: a zero/absent bid on "
                 "either leg, or a crossed/locked quote (bid >= ask)",
                 lambda d: set(d["book_bad"].dropna().unique()) <= {0, 1}),
    "spread_vs_own": ("entry spread divided by the same contract's trailing "
                      "median spread over prior sessions; >1 means the book "
                      "is wider than this contract's own norm",
                      lambda d: (d["spread_vs_own"].dropna() > 0).mean() > 0.99),
    "n_strikes": ("count of strikes quoted for the chosen expiry on entry_date",
                  lambda d: (d["n_strikes"].dropna() >= 1).mean() > 0.999),
    # A2 ECONOMIC-IDENTITY GUARD. The tick-1 gross_ret assertion checked that
    # gross_ret == (exit_mid-entry_mid)/entry_mid, which was arithmetically
    # true while exit_mid came from a DIFFERENT contract (94.1% of events).
    # Self-consistent and economically wrong. This asserts the identity that
    # actually matters: we exit the contract we bought.
    "exit_strike": ("strike actually held at exit; MUST equal the entry "
                    "strike -- we exit the contract we bought, never a "
                    "freshly-struck ATM",
                    lambda d: (np.isclose(
                        d.loc[d["exit_strike"].notna(), "exit_strike"],
                        d.loc[d["exit_strike"].notna(), "strike"]).mean()
                        > 0.999) if d["exit_strike"].notna().any() else True),
    # AMEND-4 fills semantics. EVERY fill column below covers 15:00-16:00 ET
    # ONLY -- that is the window purchased. The names say so, because the
    # previous prose said "entry day" and the capacity conclusions drawn from
    # it were wrong by an unknown multiple (ANOM-8).
    "phi_dollar_entry": ("volume-weighted dollar deviation from mid divided "
                         "by volume-weighted dollar half-spread, summed "
                         "across both straddle legs then divided ONCE -- a "
                         "ratio of sums, comparable to cost_frac. 0 = all "
                         "volume at mid, 1 = at the touch. LAST HOUR ONLY.",
                         lambda d: d["phi_dollar_entry"].dropna()
                         .between(0, 3).mean() > 0.99),
    "phi_vs_mark_entry": ("the same realised toll expressed against the "
                          "NEAR-CLOSE quoted half-spread (cost_frac) that "
                          "the backtest actually multiplies. This is the "
                          "policy-relevant phi. LAST HOUR ONLY.",
                          lambda d: d["phi_vs_mark_entry"].dropna()
                          .between(0, 3).mean() > 0.98),
    "eff_half_frac_entry": ("realised one-way toll in dollars, as a fraction "
                            "of straddle mid, both legs. LAST HOUR ONLY.",
                            lambda d: d["eff_half_frac_entry"].dropna()
                            .between(0, 1).mean() > 0.99),
    "wticks_vw_entry": ("volume-weighted quoted width in TICKS (grid is "
                        "$0.01 under $3.00, $0.05 at or above). The P2 audit "
                        "showed tick count, not spread width, governs phi: "
                        "at 1 tick no price exists strictly inside the touch.",
                        lambda d: (d["wticks_vw_entry"].dropna() >= 1)
                        .mean() > 0.99),
    "vol_lasthour_entry": ("contracts traded across both legs, 15:00-16:00 "
                           "ET ONLY. This is NOT daily volume and MUST NOT "
                           "be used as a capacity denominator (ANOM-8, "
                           "POLICY P8).",
                           lambda d: (d["vol_lasthour_entry"].dropna() >= 0)
                           .mean() > 0.999),
    "frac_vol_at_mid_lasthour_entry": ("share of last-hour volume printing "
                                       "at mid (within 5% of a half-spread)",
                                       lambda d: d["frac_vol_at_mid_lasthour_entry"]
                                       .dropna().between(0, 1).mean() > 0.999),
    "frac_vol_inside_lasthour_entry": ("share of last-hour volume printing "
                                       "strictly inside the quoted touch",
                                       lambda d: d["frac_vol_inside_lasthour_entry"]
                                       .dropna().between(0, 1).mean() > 0.999),
    "phi_sz10_entry": ("phi restricted to prints of >=10 contracts -- the "
                       "clip the strategy actually trades. The 1-lot number "
                       "is a FLOOR, not the expected fill.",
                       lambda d: d["phi_sz10_entry"].dropna()
                       .between(0, 3).mean() > 0.98),
    "phi_sz25_entry": ("phi restricted to prints of >=25 contracts (~$38k "
                       "premium at the median straddle)",
                       lambda d: d["phi_sz25_entry"].dropna()
                       .between(0, 3).mean() > 0.98),
}

# AMEND-1 (tick 1): columns that MUST vary for their guard to mean anything.
# A detector that never fires passes a domain assertion trivially -- that is
# how an all-zeros stale_dd cleared G1 at tick 1 and made guard G4 vacuous.
NON_DEGENERATE = {"stale_legs", "stale_econ", "book_bad", "cost_frac",
                  "spread_vs_own", "gross_ret", "n_strikes",
                  "phi_dollar_entry", "phi_vs_mark_entry",
                  "eff_half_frac_entry", "wticks_vw_entry",
                  "frac_vol_at_mid_lasthour_entry",
                  "frac_vol_inside_lasthour_entry",
                  "phi_sz10_entry", "phi_sz25_entry"}


def verify_semantics(df: pd.DataFrame, cols=None) -> dict:
    out = {}
    for c, (meaning, fn) in SEMANTICS.items():
        if cols and c not in cols:
            continue
        if c not in df.columns:
            out[c] = (None, meaning, "ABSENT")
            continue
        try:
            ok = bool(fn(df))
        except Exception as exc:                       # noqa: BLE001
            ok = False
            meaning = meaning + "  [assertion error: %s]" % exc
            out[c] = (ok, meaning, "FAIL")
            continue
        # AMEND-1: a domain assertion is not enough. A constant column
        # satisfies "values lie in {0,1}" while measuring nothing, so any
        # column whose guard depends on it firing must actually vary.
        if ok and c in NON_DEGENERATE and df[c].dropna().nunique() <= 1:
            out[c] = (False, meaning + "  [DEGENERATE: only %d distinct "
                      "value(s) -- the detector never fires, so it cannot "
                      "distinguish 'clean' from 'not looking'"
                      % df[c].dropna().nunique(), "FAIL")
            continue
        out[c] = (ok, meaning, "PASS" if ok else "FAIL")
    return out


UNASSERTED_OK = {"spot", "strike", "entry_spread", "exit_mid",
                 "n_trades_entry", "n_legs_entry", "med_trade_size_entry",
                 "lead_target", "dte_true", "dev_usd_entry", "half_usd_entry",
                 "phi_sz1_entry", "phi_sz5_entry", "vol_sz1_entry",
                 "vol_sz5_entry", "vol_sz10_entry", "vol_sz25_entry",
                 "dev_usd_sz1_entry", "dev_usd_sz5_entry",
                 "dev_usd_sz10_entry", "dev_usd_sz25_entry"}


def require_semantics(df: pd.DataFrame, feature: str) -> None:
    """Any graded command refuses if the feature it uses fails its assertion.

    A3: previously a column ABSENT from SEMANTICS passed silently, so any
    new column could be graded with no assertion at all -- the A2 fills
    columns went in through exactly that hole. Now an unasserted column must
    be explicitly listed in UNASSERTED_OK, which forces the choice to be
    deliberate and reviewable rather than accidental.
    """
    base = feature.split("/")[0]
    if base not in SEMANTICS:
        if base in UNASSERTED_OK:
            print("NOTE: %r has no semantic assertion (listed UNASSERTED_OK)."
                  % base)
            return
        raise SystemExit(
            "REFUSED: column %r has no entry in SEMANTICS and is not in "
            "UNASSERTED_OK. Write an assertion for what it MEANS before "
            "grading it -- an unasserted column is how this pack shipped a "
            "dead staleness detector and an exit on the wrong contract."
            % base)
    res = verify_semantics(df, cols=[base])
    if base in res and res[base][0] is False:
        raise SystemExit(
            "REFUSED: column %r fails its semantic assertion (%s). Fix the "
            "panel or the assertion before grading -- do not reinterpret the "
            "column post hoc." % (base, res[base][1]))


# ---------------------------------------------------------------------------
# panel construction
# ---------------------------------------------------------------------------

def _straddle_at(day: pd.DataFrame, spot: float, strike: float = None):
    """Straddle mid + absolute spread from one (ticker, obs_date, expiry).

    strike=None  -> pick the ATM strike (used at ENTRY, where we choose it).
    strike given -> quote THAT strike (used at EXIT: we hold the contract we
                    bought). AMENDMENT A2: previously the exit re-picked ATM
                    independently, so 94.1% of events compared the straddle
                    we bought against a freshly-struck ATM one -- which
                    understates return exactly when spot moves, i.e. when a
                    straddle wins. engine.py always did this correctly
                    ("ATM strike fixed at entry", line 345).
    """
    if day.empty:
        return None
    if strike is None:
        k = day.iloc[(day["strike"] - spot).abs().argsort()[:1]]
    else:
        k = day[np.isclose(day["strike"], strike)]
        if k.empty:
            return None
    r = k.iloc[0]
    cm, pm = (r.call_bid + r.call_ask) / 2.0, (r.put_bid + r.put_ask) / 2.0
    if not (cm > 0 and pm > 0):
        return None
    mid = cm + pm
    spread = (r.call_ask - r.call_bid) + (r.put_ask - r.put_bid)
    return {"strike": float(r.strike), "mid": float(mid),
            "spread": float(spread), "n_strikes": int(len(day)),
            "cb": float(r.call_bid), "ca": float(r.call_ask),
            "pb": float(r.put_bid), "pa": float(r.put_ask)}


def cmd_build(args) -> None:
    ev = pd.read_csv(args.events, parse_dates=["ann_date"])
    ch = pd.read_csv(args.chains, parse_dates=["obs_date", "expiry"])
    ch = ch.sort_values(["ticker", "obs_date", "expiry", "strike"])
    rows = []
    for tk, evg in ev.groupby("ticker"):
        cht = ch[ch["ticker"] == tk]
        if cht.empty:
            continue
        obs_all = np.sort(cht["obs_date"].unique())
        for _, e in evg.iterrows():
            ann, sess = e["ann_date"], str(e.get("session", "AMC")).upper()
            exps = cht.loc[cht["expiry"] > ann, "expiry"]
            if exps.empty:
                continue
            expiry = exps.min()
            # pre-print exit: AMC prints after the close, so the ann_date mark
            # is still pre-print; BMO prints before, so the last mark strictly
            # before ann_date is the pre-print one.
            ex_pool = obs_all[obs_all <= ann] if sess == "AMC" \
                else obs_all[obs_all < ann]
            if len(ex_pool) == 0:
                continue
            exit_date = ex_pool[-1]
            ce = cht[(cht["obs_date"] == exit_date) & (cht["expiry"] == expiry)]
            sp_e = ce["spot"].iloc[0] if len(ce) else np.nan
            for lead in LEADS:
                target = ann - pd.Timedelta(days=lead)
                pool = obs_all[obs_all <= target]
                if len(pool) == 0:
                    continue
                entry_date = pool[-1]
                if (target - pd.Timestamp(entry_date)).days > 4:
                    continue                      # no mark near the target lead
                cd = cht[(cht["obs_date"] == entry_date) &
                         (cht["expiry"] == expiry)]
                if cd.empty:
                    continue
                spot = cd["spot"].iloc[0]
                st = _straddle_at(cd, spot)
                if st is None:
                    continue
                # AMEND-1 (tick 1): the previous detector demanded exact
                # 4-way quote equality and fired ~0.9 times per panel, so
                # "0% stale" measured nothing. Replaced by a graded leg
                # count, an economic-staleness flag, and book-quality flags.
                prev = obs_all[obs_all < entry_date]
                stale_legs = np.nan
                stale_econ = np.nan
                if len(prev):
                    pd_ = cht[(cht["obs_date"] == prev[-1]) &
                              (cht["expiry"] == expiry) &
                              (cht["strike"] == st["strike"])]
                    if len(pd_):
                        p = pd_.iloc[0]
                        stale_legs = int((p.call_bid == st["cb"]) +
                                         (p.call_ask == st["ca"]) +
                                         (p.put_bid == st["pb"]) +
                                         (p.put_ask == st["pa"]))
                        prev_mid = ((p.call_bid + p.call_ask) / 2.0 +
                                    (p.put_bid + p.put_ask) / 2.0)
                        prev_spot = float(p.spot) if p.spot > 0 else np.nan
                        spot_moved = (abs(spot / prev_spot - 1.0) >= 0.005
                                      if np.isfinite(prev_spot) else False)
                        # a mid that does not move while the underlying does
                        # is not a price, it is a carried-forward mark
                        stale_econ = int(bool(spot_moved) and
                                         abs(prev_mid - st["mid"]) < 1e-9)
                book_bad = int(st["cb"] <= 0 or st["pb"] <= 0 or
                               st["ca"] <= st["cb"] or st["pa"] <= st["pb"])
                # entry spread vs this contract's own trailing norm
                hist = cht[(cht["obs_date"] < entry_date) &
                           (cht["expiry"] == expiry) &
                           (cht["strike"] == st["strike"])]
                sv = np.nan
                if len(hist) >= 3:
                    h = ((hist["call_ask"] - hist["call_bid"]) +
                         (hist["put_ask"] - hist["put_bid"])).median()
                    if h > 0:
                        sv = st["spread"] / float(h)
                # A2: exit on the CONTRACT WE BOUGHT (this lead's own entry
                # strike), not a freshly-struck ATM. Each lead therefore has
                # its own exit_mid -- which is why EX-5 is a real experiment
                # and not the closed-form identity ANOM-2 claimed.
                ex = _straddle_at(ce, sp_e, strike=st["strike"]) \
                    if len(ce) else None
                gross = (ex["mid"] - st["mid"]) / st["mid"] if ex else np.nan
                cost = st["spread"] / (2.0 * st["mid"])
                rows.append({
                    "ticker": tk, "ann_date": ann.date(),
                    "entry_date": pd.Timestamp(entry_date).date(),
                    "exit_date": pd.Timestamp(exit_date).date(),
                    "expiry": pd.Timestamp(expiry).date(), "session": sess,
                    "lead": int((ann - pd.Timestamp(entry_date)).days),
                    "dte_true": int((pd.Timestamp(expiry) -
                                     pd.Timestamp(entry_date)).days),
                    "lead_target": lead, "spot": spot, "strike": st["strike"],
                    "entry_mid": st["mid"], "entry_spread": st["spread"],
                    "exit_strike": (ex_k := (st["strike"] if ex else np.nan)),
                    "cost_frac": cost, "n_strikes": st["n_strikes"],
                    "stale_legs": stale_legs, "stale_econ": stale_econ,
                    "book_bad": book_bad, "spread_vs_own": sv,
                    "exit_mid": ex["mid"] if ex else np.nan,
                    "gross_ret": gross,
                })
    out = pd.DataFrame(rows)
    if out.empty:
        raise SystemExit("build produced no rows -- check inputs")
    out["season"] = (pd.to_datetime(out["ann_date"]).dt.year.astype(str) + "Q"
                     + pd.to_datetime(out["ann_date"]).dt.quarter.astype(str))
    out["event_id"] = out["ticker"] + "|" + out["ann_date"].astype(str)
    out.to_csv(args.out, index=False)
    print("wrote %s: %d rows, %d events, %d tickers, leads %s"
          % (args.out, len(out), out["event_id"].nunique(),
             out["ticker"].nunique(), sorted(out["lead_target"].unique())))
    print("sha256 %s" % sha256(args.out))
    print("\nNEXT: add the sha to SHA256SUMS, then run `dict --data %s`. "
          "Nothing may be graded before the semantics pass." % args.out)


def load(path: str, require_manifest: bool = True) -> pd.DataFrame:
    check_manifest(path, require=require_manifest)
    df = pd.read_csv(path)
    for c in ("ann_date", "entry_date", "exit_date", "expiry"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
    return df


# ---------------------------------------------------------------------------
# inference
# ---------------------------------------------------------------------------

def sign_perm_p(diffs: np.ndarray, n_perm: int = N_PERM, seed: int = SEED):
    """Exact-ish two-sided paired test: randomly flip the sign of each paired
    difference. Assumption-free, correct for heavy tails, and the right test
    for within-event policy comparison."""
    d = np.asarray([x for x in diffs if np.isfinite(x)])
    if len(d) < 8:
        return float("nan"), float("nan"), 0
    theta = float(np.median(d))
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n_perm):
        s = rng.choice([-1.0, 1.0], size=len(d))
        if abs(float(np.median(d * s))) >= abs(theta):
            hits += 1
    return theta, (hits + 1) / (n_perm + 1), len(d)


def cluster_boot_ci(values: np.ndarray, clusters: np.ndarray,
                    stat=np.median, n_boot: int = N_BOOT, seed: int = SEED):
    """Cluster bootstrap CI. Reports the number of EFFECTIVE clusters, because
    the signal pack learned the hard way that a bootstrap over 2-3 clusters
    manufactures significance."""
    v = np.asarray(values, dtype=float)
    c = np.asarray(clusters)
    ok = np.isfinite(v)
    v, c = v[ok], c[ok]
    uc = np.unique(c)
    if len(v) < 8 or len(uc) < 2:
        return float("nan"), float("nan"), float("nan"), len(uc)
    groups = {k: v[c == k] for k in uc}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(uc, size=len(uc), replace=True)
        boots.append(stat(np.concatenate([groups[k] for k in pick])))
    boots = np.asarray(boots)
    return (float(stat(v)), float(np.percentile(boots, 2.5)),
            float(np.percentile(boots, 97.5)), len(uc))


def cluster_boot_ci_stat(d: pd.DataFrame, fx: str, fy: str, cluster: str,
                         n_boot: int = 1500, seed: int = SEED):
    """A3: cluster bootstrap CI for the SPEARMAN ITSELF (the old code
    bootstrapped the median of the target and printed it beside the
    correlation). Returns (lo, hi, n_effective_clusters)."""
    uc = d[cluster].unique()
    if len(uc) < 2:
        return float("nan"), float("nan"), len(uc)
    groups = {k: g for k, g in d.groupby(cluster)}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(uc, size=len(uc), replace=True)
        s = pd.concat([groups[k] for k in pick], ignore_index=True)
        v = spearman(s[fx], s[fy])
        if np.isfinite(v):
            boots.append(v)
    if len(boots) < 50:
        return float("nan"), float("nan"), len(uc)
    return (float(np.percentile(boots, 2.5)),
            float(np.percentile(boots, 97.5)), len(uc))


def perm_p_spearman(d: pd.DataFrame, fx: str, fy: str, cluster: str,
                    n_perm: int = 1000, seed: int = SEED):
    """A3: two-sided within-cluster permutation p for a Spearman. Shuffling
    the feature inside each season removes any season-level confounding
    while preserving the null."""
    rng = np.random.default_rng(seed)
    theta = spearman(d[fx], d[fy])
    if not np.isfinite(theta):
        return float("nan")
    x = d.copy()
    hits = 0
    for _ in range(n_perm):
        x[fx] = x.groupby(cluster)[fx].transform(
            lambda s: rng.permutation(s.values))
        v = spearman(x[fx], x[fy])
        if np.isfinite(v) and abs(v) >= abs(theta):
            hits += 1
    return (hits + 1) / (n_perm + 1)


def spearman(a: pd.Series, b: pd.Series) -> float:
    x = pd.concat([a, b], axis=1).dropna()
    if len(x) < 20:
        return float("nan")
    return float(x.iloc[:, 0].rank().corr(x.iloc[:, 1].rank()))


def log_entry(entry: dict) -> str:
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    entry["id"] = "E%04d" % ((sum(1 for _ in open(LOG)) + 1)
                             if os.path.exists(LOG) else 1)
    with open(LOG, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return entry["id"]


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_dict(args) -> None:
    df = load(args.data, require_manifest=False)
    res = verify_semantics(df, cols=[args.col] if args.col else None)
    bad = 0
    for c, (ok, meaning, status) in sorted(res.items()):
        print("  [%-6s] %-11s %s" % (status, c, meaning))
        bad += (status == "FAIL")
    print("\n%d column(s) checked, %d FAIL" % (len(res), bad))
    if bad:
        raise SystemExit("SEMANTICS FAILED -- these columns may not be graded.")
    print("semantics OK; panel may be graded")


def cmd_test(args) -> None:
    df = load(args.data)
    require_semantics(df, args.feature)
    d = df[df["lead_target"] == args.lead] if args.lead else df
    xid = log_entry({"hyp": args.hyp, "cmd": " ".join(sys.argv[1:]),
                     "kind": "test", "data": os.path.basename(args.data),
                     "data_sha": sha256(args.data)[:16],
                     "feature": args.feature, "target": args.target,
                     "pred_sign": args.sign})
    # AMENDMENT A3: cmd_test previously reported NO p-value, and the ci95 it
    # printed beside the Spearman was actually a CI for median cost_frac --
    # adjacent, unlabelled, and easy to misread as the statistic's own
    # interval. No cross-sectional hypothesis could clear an alpha threshold.
    # Now: the CI is bootstrapped for the STATISTIC ITSELF, and a
    # within-season permutation p accompanies it.
    tgt = {"cost_ic": "cost_frac", "spread": "entry_spread",
           "stale": "stale_legs"}.get(args.target)
    if tgt is None:
        raise SystemExit("unknown target")
    if tgt not in d.columns:
        raise SystemExit("REFUSED: target column %r absent from this panel"
                         % tgt)
    require_semantics(d, tgt)
    sub = d[[args.feature, tgt, "season"]].dropna()
    if len(sub) < 20:
        raise SystemExit("REFUSED: only %d usable rows" % len(sub))
    stat = spearman(sub[args.feature], sub[tgt])
    stat_ci = cluster_boot_ci_stat(sub, args.feature, tgt, "season")
    p_perm = perm_p_spearman(sub, args.feature, tgt, "season")
    extra = {"target_median": round(float(sub[tgt].median()), 5)}
    sign_ok = (args.sign is None or not np.isfinite(stat)
               or (stat > 0) == (args.sign == "+"))
    print(json.dumps({"entry": xid, "n": int(len(sub)),
                      "target": tgt,
                      "stat_spearman": None if not np.isfinite(stat) else round(stat, 5),
                      "stat_ci95": [None if not np.isfinite(stat_ci[0]) else round(stat_ci[0], 5),
                                    None if not np.isfinite(stat_ci[1]) else round(stat_ci[1], 5)],
                      "perm_p": None if not np.isfinite(p_perm) else round(p_perm, 5),
                      "effective_clusters": int(stat_ci[2]),
                      "sign_matches_prediction": bool(sign_ok), **extra},
                     indent=2))
    if stat_ci[2] < 4:
        print("WARNING: %d effective clusters -- CI untrustworthy; the "
              "permutation p is the admissible read." % stat_ci[2])
    print("NOTE: stat_ci95 is the interval for the SPEARMAN itself. Spend "
          "alpha in STATE.json; a paired `policy` result outranks this.")


def cmd_policy(args) -> None:
    """Paired within-event comparison of two entry leads. THE core command."""
    df = load(args.data)
    a = df[df["lead_target"] == args.a].set_index("event_id")
    b = df[df["lead_target"] == args.b].set_index("event_id")
    common = a.index.intersection(b.index)
    if len(common) < 8:
        raise SystemExit("only %d paired events -- refusing" % len(common))
    a, b = a.loc[common], b.loc[common]
    col = {"cost": "cost_frac", "gross": "gross_ret"}[args.metric] \
        if args.metric != "net" else None
    if args.metric == "net":
        # Round trip = two crossings. Each crossing pays PHI of the one-way
        # half-spread (cost_frac), so total toll = 2*PHI*cost_frac. At the
        # inherited PHI=0.5 that equals exactly one full half-spread over the
        # round trip -- the bt.py convention the graduated result was run on.
        va = a["gross_ret"] - 2 * PHI_DEFAULT * a["cost_frac"]
        vb = b["gross_ret"] - 2 * PHI_DEFAULT * b["cost_frac"]
    else:
        va, vb = a[col], b[col]
    diffs = (va - vb).values
    xid = log_entry({"hyp": args.hyp, "cmd": " ".join(sys.argv[1:]),
                     "kind": "policy", "data": os.path.basename(args.data),
                     "data_sha": sha256(args.data)[:16],
                     "a": args.a, "b": args.b, "metric": args.metric})
    theta, p, n = sign_perm_p(diffs)
    med, lo, hi, nc = cluster_boot_ci(diffs, a["season"].values)
    wins = float(np.mean([x > 0 for x in diffs if np.isfinite(x)]))
    print(json.dumps({
        "entry": xid, "paired_events": int(n),
        "metric": args.metric, "a_lead": args.a, "b_lead": args.b,
        "median_diff_a_minus_b": None if not np.isfinite(theta) else round(theta, 5),
        "perm_p": None if not np.isfinite(p) else round(p, 5),
        "ci95": [None if not np.isfinite(lo) else round(lo, 5),
                 None if not np.isfinite(hi) else round(hi, 5)],
        "effective_clusters": int(nc),
        "frac_a_greater": round(wins, 4),
        "a_median": round(float(np.nanmedian(va)), 5),
        "b_median": round(float(np.nanmedian(vb)), 5),
    }, indent=2))
    if nc < 4:
        print("WARNING: %d effective clusters -- CI is not trustworthy; "
              "the permutation p is the admissible read." % nc)


def cmd_admit(args) -> None:
    """Grade a screen on BOTH sides: what it saves and what it gives up."""
    df = load(args.data)
    d = df[df["lead_target"] == args.lead].copy()
    col, op, val = None, None, None
    for o in ("<=", ">=", "<", ">"):
        if o in args.screen:
            col, op, val = args.screen.partition(o)[0].strip(), o, \
                float(args.screen.partition(o)[2])
            break
    if col is None:
        raise SystemExit("screen must look like 'cost_frac<=0.08'")
    require_semantics(d, col)
    m = {"<=": d[col] <= val, ">=": d[col] >= val,
         "<": d[col] < val, ">": d[col] > val}[op]
    d = d.dropna(subset=["gross_ret", "cost_frac"])
    m = m.loc[d.index]
    xid = log_entry({"hyp": args.hyp, "cmd": " ".join(sys.argv[1:]),
                     "kind": "admit", "data": os.path.basename(args.data),
                     "data_sha": sha256(args.data)[:16],
                     "screen": args.screen, "lead": args.lead})
    net = d["gross_ret"] - PHI_DEFAULT * 2 * d["cost_frac"]
    adm, rej = d[m], d[~m]
    tail_thr = 0.50
    out = {
        "entry": xid, "screen": args.screen, "lead": args.lead,
        "n_total": int(len(d)), "n_admitted": int(m.sum()),
        "admitted_frac": round(float(m.mean()), 4),
        "cost_median_admitted": round(float(adm["cost_frac"].median()), 5),
        "cost_median_rejected": round(float(rej["cost_frac"].median()), 5)
        if len(rej) else None,
        "gross_median_admitted": round(float(adm["gross_ret"].median()), 5),
        "gross_median_rejected": round(float(rej["gross_ret"].median()), 5)
        if len(rej) else None,
        "net_median_admitted": round(float(net[m].median()), 5),
        "net_median_all": round(float(net.median()), 5),
        "gross_tail_rate_admitted": round(
            float((adm["gross_ret"] >= tail_thr).mean()), 4),
        "gross_tail_rate_rejected": round(
            float((rej["gross_ret"] >= tail_thr).mean()), 4) if len(rej) else None,
        "foregone_gross_tail_events": int((rej["gross_ret"] >= tail_thr).sum())
        if len(rej) else 0,
    }
    theta, p, n = sign_perm_p((net[m]).values - float(net.median()))
    out["net_shift_vs_all_median"] = None if not np.isfinite(theta) else round(theta, 5)
    out["net_shift_perm_p"] = None if not np.isfinite(p) else round(p, 5)
    print(json.dumps(out, indent=2))
    print("READ BOTH NUMBERS: a screen that lowers cost while discarding "
          "gross-tail events can destroy the strategy it was meant to protect.")


# ---------------------------------------------------------------------------
# fills panel (AMENDMENT A2) -- what the tape says we would actually pay
# ---------------------------------------------------------------------------

TCBBO_DIR = os.path.join(os.path.dirname(HERE), "data", "raw", "db_tcbbo")


def osi(root: str, expiry, cp: str, strike: float) -> str:
    """OPRA OSI symbol: root padded to 6, YYMMDD, C/P, strike*1000 in 8 digits.
    e.g. 'TSLA  230505C00200000'."""
    e = pd.Timestamp(expiry)
    return "%-6s%02d%02d%02d%s%08d" % (root, e.year % 100, e.month, e.day,
                                       cp, int(round(strike * 1000)))


def _tick_size(mid: float) -> float:
    """OPRA price grid: $0.01 below $3.00, $0.05 at or above. Recorded as an
    assumption -- it drives the width-in-ticks bucketing, and the P2 audit
    showed tick count, not spread width, is what actually governs phi."""
    return 0.01 if mid < 3.0 else 0.05


def cmd_fills(args) -> None:
    """Join tcbbo prints to the contracts we would actually have traded.

    AMEND-4 changes three things the P2 audit found wrong:
      (a) DOLLAR-CONSISTENT AGGREGATION. Previously eff_half_frac was a mean
          of per-leg RATIOS while cost_frac is a RATIO OF STRADDLE SUMS, and
          phi_implied was a third convention (equal-weighting contracts
          regardless of dollars at stake). phi_B happened to be robust
          because the two errors cancelled; phi_A was not -- dollar-correct
          it is 0.478 with a CI containing 0.50, so "0.5 is too kind" was an
          artifact. Everything is now a ratio of volume-weighted dollar sums.
      (b) HONEST NAMING. Every fill quantity here covers 15:00-16:00 ET ONLY,
          because that is the window we purchased. Columns say so. Full-day
          volume is NOT derivable from this data, so no capacity rule can be
          written (POLICY P8 stays BLOCKED).
      (c) SIZE AND WIDTH CONDITIONING. phi is reported at minimum clip sizes
          {1,5,10,25} and by quoted width in ticks, which the audit showed is
          the correct functional form: in a 1-tick market no price exists
          strictly inside the touch, so phi is pinned near 1 by arithmetic.
    """
    p = pd.read_csv(args.panel, parse_dates=["ann_date", "entry_date",
                                             "exit_date", "expiry"])
    need = {}
    for _, r in p.iterrows():
        if not np.isfinite(r["strike"]):
            continue
        for role, d in (("entry", r["entry_date"]), ("exit", r["exit_date"])):
            key = pd.Timestamp(d).date().isoformat()
            for leg, cp in (("call", "C"), ("put", "P")):
                sym = osi(r["ticker"], r["expiry"], cp, r["strike"])
                need.setdefault(key, {}).setdefault(sym, []).append(
                    (r["event_id"], int(r["lead_target"]), role, leg))
    SIZES = [1, 5, 10, 25]
    rows = []
    files = sorted(f for f in os.listdir(TCBBO_DIR) if f.endswith(".csv.gz"))
    for i, fn in enumerate(files, 1):
        d = fn.replace(".csv.gz", "")
        if d not in need:
            continue
        df = pd.read_csv(os.path.join(TCBBO_DIR, fn),
                         usecols=["ts_event", "price", "size", "bid_px_00",
                                  "ask_px_00", "bid_sz_00", "ask_sz_00",
                                  "symbol"])
        df = df[df["symbol"].isin(need[d])]
        if df.empty:
            continue
        bid, ask = df["bid_px_00"], df["ask_px_00"]
        mid = 0.5 * (bid + ask)
        half = 0.5 * (ask - bid)
        ok = (bid > 0) & (ask > bid) & (mid > 0) & (df["price"] > 0)
        df, mid, half = df[ok], mid[ok], half[ok]
        if df.empty:
            continue
        tick = mid.map(_tick_size)
        df = df.assign(_mid=mid, _half=half,
                       _dev=(df["price"] - mid).abs(),
                       _wticks=((ask[ok] - bid[ok]) / tick).round().clip(1, 99))
        for sym, g in df.groupby("symbol"):
            v = g["size"].astype(float)
            V = float(v.sum())
            if V <= 0:
                continue
            # ratio of volume-weighted DOLLAR sums, not a mean of ratios
            dev_d = float((g["_dev"] * v).sum() / V)
            half_d = float((g["_half"] * v).sum() / V)
            rec = {"obs": d, "symbol": sym, "n_trades": int(len(g)),
                   "vol_lasthour": V, "dev_usd": dev_d, "half_usd": half_d,
                   "wticks_vw": float((g["_wticks"] * v).sum() / V),
                   "frac_vol_at_mid_lasthour":
                       float(v[g["_dev"] <= 0.05 * g["_half"]].sum() / V),
                   "frac_vol_inside_lasthour":
                       float(v[g["_dev"] < 0.999 * g["_half"]].sum() / V),
                   "med_trade_size": float(v.median())}
            for z in SIZES:
                m = g["size"] >= z
                vz = v[m]
                Vz = float(vz.sum())
                rec["dev_usd_sz%d" % z] = (
                    float((g.loc[m, "_dev"] * vz).sum() / Vz) if Vz > 0 else np.nan)
                rec["half_usd_sz%d" % z] = (
                    float((g.loc[m, "_half"] * vz).sum() / Vz) if Vz > 0 else np.nan)
                rec["vol_sz%d" % z] = Vz
            for (eid, lead, role, leg) in need[d][sym]:
                rows.append({**rec, "event_id": eid, "lead_target": lead,
                             "role": role, "leg": leg})
        if i % 60 == 0:
            print("  scanned %d/%d files, %d leg-rows" % (i, len(files), len(rows)))
    if not rows:
        raise SystemExit("no fills matched -- check symbol construction")
    f = pd.DataFrame(rows)

    def _combine(g):
        out = {"n_legs": g["leg"].nunique(),
               "n_trades": g["n_trades"].sum(),
               "vol_lasthour": g["vol_lasthour"].sum(),
               "wticks_vw": np.average(g["wticks_vw"], weights=g["vol_lasthour"]),
               "med_trade_size": g["med_trade_size"].median()}
        # straddle dollars = call leg + put leg, then take the ratio ONCE
        dev = g["dev_usd"].sum()
        hlf = g["half_usd"].sum()
        out["dev_usd"] = dev
        out["half_usd"] = hlf
        out["phi_dollar"] = dev / hlf if hlf > 0 else np.nan
        for z in SIZES:
            dz, hz = g["dev_usd_sz%d" % z].sum(), g["half_usd_sz%d" % z].sum()
            out["phi_sz%d" % z] = dz / hz if hz > 0 else np.nan
            out["dev_usd_sz%d" % z] = dz
            out["vol_sz%d" % z] = g["vol_sz%d" % z].sum()
        for c in ("frac_vol_at_mid_lasthour", "frac_vol_inside_lasthour"):
            out[c] = np.average(g[c], weights=g["vol_lasthour"])
        return pd.Series(out)

    agg = (f.groupby(["event_id", "lead_target", "role"])
             .apply(_combine, include_groups=False).reset_index())
    wide = agg.pivot(index=["event_id", "lead_target"], columns="role")
    wide.columns = ["%s_%s" % (a, b) for a, b in wide.columns]
    out = p.merge(wide.reset_index(), on=["event_id", "lead_target"], how="left")
    # phi against the near-close mark the backtest actually multiplies
    if "dev_usd_entry" in out.columns:
        out["eff_half_frac_entry"] = out["dev_usd_entry"] / out["entry_mid"]
        out["phi_vs_mark_entry"] = out["eff_half_frac_entry"] / out["cost_frac"]
    out.to_csv(args.out, index=False)
    m = out["phi_dollar_entry"].notna()
    e = out[m]
    print("\nwrote %s: %d rows, %d with entry fills (%.1f%%)"
          % (args.out, len(out), int(m.sum()), 100 * m.mean()))
    print("sha256 %s" % sha256(args.out))
    print("\nHEADLINE (descriptive, ungraded). ALL FIGURES 15:00-16:00 ET ONLY.")
    print("  phi vs TRADE-TIME half-spread (dollar-consistent): median %.3f"
          % e["phi_dollar_entry"].median())
    print("  phi vs NEAR-CLOSE mark (what the backtest multiplies): median %.3f"
          % e["phi_vs_mark_entry"].median())
    print("  incumbent assumption: %.2f" % PHI_DEFAULT)
    print("\n  phi by minimum clip size (the strategy does not trade 1-lots):")
    for z in SIZES:
        c = "phi_sz%d_entry" % z
        sub = e[c].dropna()
        print("    >= %2d contracts : n=%3d  median phi %.3f"
              % (z, len(sub), sub.median() if len(sub) else float("nan")))
    print("\n  phi by quoted width in ticks (no interior price exists at 1 tick):")
    for lo, hi, lbl in ((0.5, 1.5, "1"), (1.5, 2.5, "2"), (2.5, 4.5, "3-4"),
                        (4.5, 8.5, "5-8"), (8.5, 999, ">8")):
        sub = e[(e["wticks_vw_entry"] >= lo) & (e["wticks_vw_entry"] < hi)]
        if len(sub):
            print("    %-4s ticks : n=%3d  median phi %.3f  frac inside %.3f"
                  % (lbl, len(sub), sub["phi_dollar_entry"].median(),
                     sub["frac_vol_inside_lasthour_entry"].median()))
    print("\nNEXT: add sha to SHA256SUMS, then `dict --data %s`." % args.out)


def cmd_selftest(args) -> None:
    rng = np.random.default_rng(11)
    n_ev, checks = 400, []
    ev = ["T%03d|2025-01-15" % i for i in range(n_ev)]
    # planted: lead 3 costs less than lead 14 on the same event, by 2pp median
    base = rng.uniform(0.04, 0.20, n_ev)
    rows = []
    for i, e in enumerate(ev):
        for lead in (3, 14):
            c = base[i] + (-0.02 if lead == 3 else 0.0) + rng.normal(0, 0.005)
            rows.append({"event_id": e, "lead_target": lead,
                         "cost_frac": max(c, 0.001),
                         "gross_ret": rng.normal(0.03, 0.30),
                         "season": "S%d" % (i % 8),
                         "entry_spread": c * 2, "stale_dd": int(rng.random() < .1),
                         "noise": rng.normal()})
    d = pd.DataFrame(rows)
    a = d[d.lead_target == 3].set_index("event_id")
    b = d[d.lead_target == 14].set_index("event_id")
    theta, p, n = sign_perm_p((a["cost_frac"] - b["cost_frac"]).values)
    checks.append(("paired: planted cost edge detected",
                   p < 0.05 and theta < -0.01, "med %.4f p %.4f n %d"
                   % (theta, p, n)))
    theta2, p2, _ = sign_perm_p((a["gross_ret"].values - b["gross_ret"].values))
    checks.append(("paired: null gross difference not detected", p2 > 0.05,
                   "med %.4f p %.4f" % (theta2, p2)))
    ic = spearman(d["entry_spread"], d["cost_frac"])
    checks.append(("cost_ic: mechanical link recovered", ic > 0.9,
                   "ic %.3f" % ic))
    icn = spearman(d["noise"], d["cost_frac"])
    checks.append(("cost_ic: null feature rejected", abs(icn) < 0.15,
                   "ic %.3f" % icn))
    _, lo, hi, nc = cluster_boot_ci(
        (a["cost_frac"] - b["cost_frac"]).values, a["season"].values)
    checks.append(("cluster CI excludes zero on planted effect",
                   np.isfinite(hi) and hi < 0, "ci [%.4f, %.4f] clusters %d"
                   % (lo, hi, nc)))
    # semantics guard must FAIL a mislabelled column (the H12 scenario)
    bad = pd.DataFrame({"ann_date": pd.to_datetime(["2025-01-15"] * 5),
                        "entry_date": pd.to_datetime(["2025-01-01"] * 5),
                        "lead": [99] * 5})
    res = verify_semantics(bad, cols=["lead"])
    checks.append(("semantics guard rejects a mislabelled column",
                   res["lead"][0] is False, res["lead"][2]))
    good = bad.copy(); good["lead"] = 14
    res2 = verify_semantics(good, cols=["lead"])
    checks.append(("semantics guard passes a correct column",
                   res2["lead"][0] is True, res2["lead"][2]))
    # AMEND-1 regression: the tick-1 defect was an all-zeros detector that
    # satisfied its domain assertion. It must now FAIL as degenerate.
    dead = pd.DataFrame({"stale_econ": [0] * 200})
    r3 = verify_semantics(dead, cols=["stale_econ"])
    checks.append(("degenerate detector REJECTED (the tick-1 defect)",
                   r3["stale_econ"][0] is False, r3["stale_econ"][2]))
    alive = pd.DataFrame({"stale_econ": [0] * 190 + [1] * 10})
    r4 = verify_semantics(alive, cols=["stale_econ"])
    checks.append(("varying detector accepted",
                   r4["stale_econ"][0] is True, r4["stale_econ"][2]))
    graded = pd.DataFrame({"stale_legs": [0, 1, 2, 3, 4] * 40})
    r5 = verify_semantics(graded, cols=["stale_legs"])
    checks.append(("graded leg-count column accepted",
                   r5["stale_legs"][0] is True, r5["stale_legs"][2]))
    outdom = pd.DataFrame({"stale_legs": [0, 1, 7] * 40})
    r6 = verify_semantics(outdom, cols=["stale_legs"])
    checks.append(("out-of-domain leg count rejected",
                   r6["stale_legs"][0] is False, r6["stale_legs"][2]))
    # A2 regression: the economic-identity guard must catch an exit on a
    # DIFFERENT contract -- the exact defect that survived tick 1 because the
    # column was arithmetically self-consistent.
    wrongk = pd.DataFrame({"strike": [100.0] * 50,
                           "exit_strike": [95.0] * 50})
    r7 = verify_semantics(wrongk, cols=["exit_strike"])
    checks.append(("exit-on-different-contract REJECTED (A2 defect)",
                   r7["exit_strike"][0] is False, r7["exit_strike"][2]))
    rightk = pd.DataFrame({"strike": [100.0] * 50,
                           "exit_strike": [100.0] * 50})
    r8 = verify_semantics(rightk, cols=["exit_strike"])
    checks.append(("exit-on-held-contract accepted",
                   r8["exit_strike"][0] is True, r8["exit_strike"][2]))
    # phi domain guard
    badphi = pd.DataFrame({"phi_dollar_entry": [0.5, 0.6, 9.9] * 40})
    r9 = verify_semantics(badphi, cols=["phi_dollar_entry"])
    checks.append(("out-of-domain phi rejected",
                   r9["phi_dollar_entry"][0] is False,
                   r9["phi_dollar_entry"][2]))
    # A3 regressions: the three defects tick 2 exposed.
    import pandas as _pd
    sd = _pd.DataFrame({"season": ["S%d" % (i % 6) for i in range(300)],
                        "x": rng.normal(size=300)})
    sd["y"] = sd["x"] * 0.6 + rng.normal(size=300) * 0.8
    lo_, hi_, nc_ = cluster_boot_ci_stat(sd, "x", "y", "season")
    checks.append(("A3: CI is for the STATISTIC and excludes 0 on planted",
                   np.isfinite(lo_) and lo_ > 0.2, "ci [%.3f, %.3f] k=%d"
                   % (lo_, hi_, nc_)))
    pp = perm_p_spearman(sd, "x", "y", "season", n_perm=200)
    checks.append(("A3: perm p detects planted correlation", pp < 0.05,
                   "p %.4f" % pp))
    sn = sd.copy(); sn["y"] = rng.normal(size=300)
    pn = perm_p_spearman(sn, "x", "y", "season", n_perm=200)
    checks.append(("A3: perm p rejects null correlation", pn > 0.05,
                   "p %.4f" % pn))
    try:
        require_semantics(_pd.DataFrame({"mystery": [1, 2, 3]}), "mystery")
        unass = False
    except SystemExit:
        unass = True
    checks.append(("A3: unasserted column REFUSED (ANOM-4)", unass,
                   "SystemExit" if unass else "passed silently"))
    checks.append(("A3: stale target maps to a live column (ANOM-7)",
                   "stale_legs" in SEMANTICS and "stale_dd" not in SEMANTICS,
                   "stale_legs present, stale_dd gone"))
    ok = True
    for name, cond, detail in checks:
        print("  [%s] %-46s %s" % ("PASS" if cond else "FAIL", name, detail))
        ok &= bool(cond)
    if not ok:
        raise SystemExit("EXEC HARNESS SELFTEST FAILED")
    print("EXEC HARNESS SELFTEST PASSED (%d checks)" % len(checks))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--chains", required=True)
    b.add_argument("--events", required=True)
    b.add_argument("--out", required=True)
    b.set_defaults(func=cmd_build)

    d = sub.add_parser("dict")
    d.add_argument("--data", required=True)
    d.add_argument("--col", default=None)
    d.set_defaults(func=cmd_dict)

    t = sub.add_parser("test")
    t.add_argument("--data", required=True)
    t.add_argument("--feature", required=True)
    t.add_argument("--target", default="cost_ic",
                   choices=["cost_ic", "spread", "stale"])
    t.add_argument("--lead", type=int, default=None)
    t.add_argument("--hyp", default="unregistered")
    t.add_argument("--sign", default=None, choices=["+", "-"])
    t.set_defaults(func=cmd_test)

    po = sub.add_parser("policy")
    po.add_argument("--data", required=True)
    po.add_argument("--a", type=int, required=True)
    po.add_argument("--b", type=int, required=True)
    po.add_argument("--metric", default="cost", choices=["cost", "gross", "net"])
    po.add_argument("--hyp", default="unregistered")
    po.set_defaults(func=cmd_policy)

    ad = sub.add_parser("admit")
    ad.add_argument("--data", required=True)
    ad.add_argument("--screen", required=True)
    ad.add_argument("--lead", type=int, default=14)
    ad.add_argument("--hyp", default="unregistered")
    ad.set_defaults(func=cmd_admit)

    fl = sub.add_parser("fills")
    fl.add_argument("--panel", required=True)
    fl.add_argument("--out", required=True)
    fl.set_defaults(func=cmd_fills)

    s = sub.add_parser("selftest")
    s.set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
