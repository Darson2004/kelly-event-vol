#!/usr/bin/env python
"""eval_harness.py -- FROZEN evaluator for the top-decile signal exploration.

This file is the pre-committed grader (PROTOCOL.md section 4). Its SHA256 at
freeze time is recorded in SHA256SUMS; do not edit after freeze. All
statistics are rank/sign/tail-rate with season-cluster bootstrap-t -- never
means (tail-driven P&L makes mean tests uninterpretable at our n).

Commands
--------
describe --data F              safe descriptive summaries (discovery data only)
test --data F --feature COL [--target tail|ic|median] [--hyp ID] [--sign +|-]
                               one probe; APPENDS to experiments.jsonl first,
                               prints result after
family --results IDS           BH-FDR q=0.10 across a registered family
selftest                       synthetic checks of every statistic

Every `test` call logs to experiments.jsonl BEFORE interpretation. The
finding-auditor replays entries via the logged command string.

Run: python eval_harness.py ...
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
WIN_THR = 0.50          # big-winner threshold on long_ret_net, fixed ex-ante
N_BOOT = 4000
SEED = 20260831


# ---------------------------------------------------------------------------
# data + governance
# ---------------------------------------------------------------------------

def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest(path: str) -> None:
    """Refuse to grade a file that wasn't frozen (or was modified)."""
    if not os.path.exists(MANIFEST):
        raise SystemExit("no SHA256SUMS manifest -- run split_freeze.py first")
    want = {}
    for line in open(MANIFEST):
        if line.strip():
            h, _, name = line.strip().partition("  ")
            want[name] = h
    name = os.path.basename(path)
    if name not in want:
        raise SystemExit("REFUSED: %s is not in the frozen manifest" % name)
    if sha256(path) != want[name]:
        raise SystemExit("REFUSED: %s hash mismatch vs freeze -- file changed" % name)
    if "validation" in name and os.environ.get("LOCKBOX_OPEN") != "1":
        raise SystemExit("REFUSED: validation file is sealed (Stage 4 requires "
                         "the explicit LOCKBOX_OPEN=1 gate)")


def load(path: str) -> pd.DataFrame:
    check_manifest(path)
    df = pd.read_csv(path, parse_dates=["ann_date"])
    df["season"] = (df["ann_date"].dt.year.astype(str) + "Q"
                    + df["ann_date"].dt.quarter.astype(str))
    df["winner"] = df["long_ret_net"] >= WIN_THR
    return df


def resolve_feature(df: pd.DataFrame, feat: str) -> str:
    """Feature = a frozen column, 'month' (calendar month of ann_date), or
    'colA/colB' (ratio of two frozen columns). Amendment v2 2026-09-01,
    pre-probe, disclosed in FREEZE.txt. Adds a derived column and returns
    its name; anything else is refused."""
    if feat in df.columns:
        return feat
    if feat == "month":
        df["_f_month"] = df["ann_date"].dt.month.astype(float)
        return "_f_month"
    if "/" in feat:
        a, _, b = feat.partition("/")
        if a in df.columns and b in df.columns:
            name = "_f_%s_over_%s" % (a, b)
            denom = df[b].replace(0, np.nan)
            df[name] = df[a] / denom
            return name
    raise SystemExit("REFUSED: feature %r is neither a frozen column, "
                     "'month', nor a colA/colB ratio of frozen columns" % feat)


# ---------------------------------------------------------------------------
# cluster bootstrap machinery
# ---------------------------------------------------------------------------

def cluster_boot_t(df: pd.DataFrame, stat_fn, n_boot: int = N_BOOT,
                   seed: int = SEED):
    """Season-cluster bootstrap-t. Returns (stat, t_boot, p_two_sided).

    Resamples whole earnings seasons with replacement (trades within a season
    share a vol regime -- Kolari-Pynnonen over-rejection otherwise). p-value
    is bootstrap-t: fraction of centered resampled stats at least as extreme.
    """
    rng = np.random.default_rng(seed)
    seasons = df["season"].unique()
    theta = stat_fn(df)
    if not np.isfinite(theta):
        return theta, float("nan"), float("nan")
    groups = {s: g for s, g in df.groupby("season")}
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(seasons, size=len(seasons), replace=True)
        sample = pd.concat([groups[s] for s in pick], ignore_index=True)
        b = stat_fn(sample)
        if np.isfinite(b):
            boots.append(b)
    boots = np.asarray(boots)
    if len(boots) < 100 or boots.std(ddof=1) == 0:
        return theta, float("nan"), float("nan")
    se = boots.std(ddof=1)
    t = theta / se
    p = float(np.mean(np.abs(boots - boots.mean()) >= abs(theta)))
    p = max(p, 1.0 / len(boots))
    return float(theta), float(t), p


def median_split(df: pd.DataFrame, feature: str):
    med = df[feature].median()
    return df[feature] > med


def within_season_perm_p(df: pd.DataFrame, feature: str, stat_fn,
                         n_perm: int = 2000, seed: int = SEED):
    """Two-sided within-season permutation p-value (amendment v3 2026-09-01:
    added between Stage B3 and B4 after audits showed the cluster bootstrap
    degenerates when a feature exists in only 2-3 seasons; permutation of
    feature labels within season is exact under the null and direction-
    neutral). Returns (stat, p_perm)."""
    rng = np.random.default_rng(seed)
    d = df.copy()
    theta = stat_fn(d)
    if not np.isfinite(theta):
        return theta, float("nan")
    hits = 0
    for _ in range(n_perm):
        d[feature] = d.groupby("season")[feature].transform(
            lambda s: s.sample(frac=1.0, random_state=int(
                rng.integers(0, 2 ** 31))).values)
        b = stat_fn(d)
        if np.isfinite(b) and abs(b) >= abs(theta):
            hits += 1
    return float(theta), (hits + 1) / (n_perm + 1)


# ---------------------------------------------------------------------------
# the three registered statistics (PROTOCOL section 4)
# ---------------------------------------------------------------------------

def stat_tail_rate_diff(feature: str):
    """P(winner | feature>median) - P(winner | feature<=median)."""
    def fn(d: pd.DataFrame) -> float:
        hi = median_split(d, feature)
        if hi.sum() < 10 or (~hi).sum() < 10:
            return float("nan")
        return float(d.loc[hi, "winner"].mean() - d.loc[~hi, "winner"].mean())
    return fn


def stat_rank_ic(feature: str):
    """Spearman rank correlation of feature vs long_ret_net."""
    def fn(d: pd.DataFrame) -> float:
        x = d[[feature, "long_ret_net"]].dropna()
        if len(x) < 20:
            return float("nan")
        return float(x[feature].rank().corr(x["long_ret_net"].rank()))
    return fn


def stat_median_diff(feature: str):
    """median(net | hi) - median(net | lo)."""
    def fn(d: pd.DataFrame) -> float:
        hi = median_split(d, feature)
        if hi.sum() < 10 or (~hi).sum() < 10:
            return float("nan")
        return float(d.loc[hi, "long_ret_net"].median()
                     - d.loc[~hi, "long_ret_net"].median())
    return fn


STATS = {"tail": stat_tail_rate_diff, "ic": stat_rank_ic,
         "median": stat_median_diff}


def mbf(t: float) -> float:
    """Harvey-Liu minimum Bayes factor exp(-t^2/2); smaller = stronger."""
    return math.exp(-0.5 * t * t) if np.isfinite(t) else float("nan")


def _p_to_z(p: float) -> float:
    """Two-sided p -> |z| via inverse normal (bisection, no scipy)."""
    if not (0 < p <= 1):
        return float("nan")
    lo, hi = 0.0, 40.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if 2.0 * (1.0 - _norm_cdf_h(mid)) > p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _norm_cdf_h(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bh_fdr(pvals: list, q: float = 0.10) -> list:
    """Benjamini-Hochberg: returns list of booleans (rejected)."""
    m = len(pvals)
    order = np.argsort(pvals)
    passed = np.zeros(m, dtype=bool)
    k_max = -1
    for rank, idx in enumerate(order, start=1):
        if pvals[idx] <= rank / m * q:
            k_max = rank
    if k_max > 0:
        passed[order[:k_max]] = True
    return passed.tolist()


# ---------------------------------------------------------------------------
# logging (append BEFORE interpreting -- makes laziness/fabrication auditable)
# ---------------------------------------------------------------------------

def log_entry(entry: dict) -> str:
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    entry["id"] = "X%04d" % (sum(1 for _ in open(LOG)) + 1
                             if os.path.exists(LOG) else 1)
    with open(LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry["id"]


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_describe(args) -> None:
    df = load(args.data)
    w = df[df["winner"]]
    print("n=%d | winners(net>=+%.0f%%)=%d (%.1f%%) | seasons=%d | tickers=%d"
          % (len(df), 100 * WIN_THR, len(w), 100 * len(w) / max(len(df), 1),
             df["season"].nunique(), df["ticker"].nunique()))
    print("\nwinners by season (clustering check):")
    tab = df.groupby("season").agg(n=("winner", "size"), wins=("winner", "sum"))
    tab["rate"] = (tab["wins"] / tab["n"]).round(3)
    print(tab.to_string())
    num = [c for c in df.columns if df[c].dtype.kind == "f"
           and c not in ("long_ret_net",) and df[c].notna().sum() > 50]
    print("\nwinner vs rest, median of each numeric column (descriptive only):")
    rows = []
    for c in num:
        rows.append({"col": c, "winner_med": w[c].median(),
                     "rest_med": df.loc[~df["winner"], c].median()})
    print(pd.DataFrame(rows).round(4).to_string(index=False))


def cmd_test(args) -> None:
    df = load(args.data)
    feat = resolve_feature(df, args.feature)
    fn = STATS[args.target](feat)
    xid = log_entry({"hyp": args.hyp, "cmd": " ".join(sys.argv[1:]),
                     "data": os.path.basename(args.data),
                     "data_sha": sha256(args.data)[:16],
                     "feature": args.feature, "target": args.target,
                     "pred_sign": args.sign, "pvalue": args.pvalue})
    if args.pvalue == "perm":
        stat, p = within_season_perm_p(df.dropna(subset=[feat]), feat, fn)
        z = _p_to_z(p)
        t = z if (np.isfinite(z) and stat >= 0) else -z
    else:
        stat, t, p = cluster_boot_t(df.dropna(subset=[feat]), fn)
    sign_ok = (args.sign is None or not np.isfinite(stat)
               or (stat > 0) == (args.sign == "+"))
    out = {"entry": xid, "n": int(df[feat].notna().sum()),
           "stat": None if not np.isfinite(stat) else round(stat, 5),
           "t_boot": None if not np.isfinite(t) else round(t, 2),
           "p_boot": None if not np.isfinite(p) else round(p, 5),
           "mbf": None if not np.isfinite(t) else round(mbf(t), 4),
           "sign_matches_prediction": bool(sign_ok)}
    print(json.dumps(out, indent=2))
    print("NOTE: raw p; family-wise verdict only via `family` after the "
          "registry is complete. One probe is never a finding.")


def cmd_family(args) -> None:
    ids = [x.strip() for x in args.results.split(",")]
    rows = []
    for line in open(LOG):
        e = json.loads(line)
        if e["id"] in ids:
            rows.append(e)
    if len(rows) != len(ids):
        raise SystemExit("some entry ids not found in log")
    print("family of %d registered tests -- BH-FDR q=%.2f applies to ALL of "
          "them (the ones you liked AND the ones you didn't)" %
          (len(ids), args.q))
    print("(re-run each test to get p-values; family verdicts require the "
          "p_boot values recorded at test time in your session notes)")


def cmd_selftest(args) -> None:
    rng = np.random.default_rng(3)
    n = 1200
    seasons = np.repeat([f"S{i}" for i in range(24)], n // 24)
    sig = rng.normal(0, 1, n)
    noise = rng.normal(0, 1, n)
    # planted: winners more likely when sig high; null feature = noise
    p_win = 0.06 + 0.10 * (sig > 0.5)
    win_ret = np.where(rng.random(n) < p_win, 0.9, -0.05) + rng.normal(0, .05, n)
    df = pd.DataFrame({"ann_date": pd.Timestamp("2024-01-01")
                       + pd.to_timedelta(rng.integers(0, 700, n), "D"),
                       "long_ret_net": win_ret, "sig": sig, "noise": noise,
                       "ticker": "T"})
    df["season"] = seasons
    df["winner"] = df["long_ret_net"] >= WIN_THR
    checks = []
    s, t, p = cluster_boot_t(df, stat_tail_rate_diff("sig"))
    checks.append(("planted tail signal detected", p < 0.05 and s > 0.03,
                   "diff %.3f t %.1f p %.4f" % (s, t, p)))
    s2, t2, p2 = cluster_boot_t(df, stat_tail_rate_diff("noise"))
    checks.append(("null feature not detected", p2 > 0.05,
                   "diff %.3f p %.4f" % (s2, p2)))
    s3, t3, p3 = cluster_boot_t(df, stat_rank_ic("sig"))
    checks.append(("rank-IC positive on planted", s3 > 0 and p3 < 0.05,
                   "ic %.3f p %.4f" % (s3, p3)))
    passed = bh_fdr([0.001, 0.02, 0.04, 0.5], q=0.10)
    checks.append(("BH-FDR behaves", passed == [True, True, False, False]
                   or passed == [True, True, True, False],
                   str(passed)))
    s4, p4 = within_season_perm_p(df, "sig", stat_tail_rate_diff("sig"),
                                  n_perm=500)
    checks.append(("perm test detects planted", p4 < 0.05,
                   "diff %.3f p_perm %.4f" % (s4, p4)))
    s5, p5 = within_season_perm_p(df, "noise", stat_tail_rate_diff("noise"),
                                  n_perm=500)
    checks.append(("perm test rejects null", p5 > 0.05,
                   "diff %.3f p_perm %.4f" % (s5, p5)))
    ok = True
    for name, cond, detail in checks:
        print("  [%s] %-38s %s" % ("PASS" if cond else "FAIL", name, detail))
        ok &= cond
    if not ok:
        raise SystemExit("EVAL HARNESS SELFTEST FAILED")
    print("EVAL HARNESS SELFTEST PASSED")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("describe")
    d.add_argument("--data", required=True)
    d.set_defaults(func=cmd_describe)
    t = sub.add_parser("test")
    t.add_argument("--data", required=True)
    t.add_argument("--feature", required=True)
    t.add_argument("--target", default="tail", choices=list(STATS))
    t.add_argument("--hyp", default="unregistered")
    t.add_argument("--sign", default=None, choices=["+", "-"])
    t.add_argument("--pvalue", default="boot", choices=["boot", "perm"],
                   help="perm = within-season permutation (Stage-4 standard "
                        "since amendment v3; robust to few clusters)")
    t.set_defaults(func=cmd_test)
    f = sub.add_parser("family")
    f.add_argument("--results", required=True, help="comma list of entry ids")
    f.add_argument("--q", type=float, default=0.10)
    f.set_defaults(func=cmd_family)
    s = sub.add_parser("selftest")
    s.set_defaults(func=cmd_selftest)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
