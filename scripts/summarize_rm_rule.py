#!/usr/bin/env python
"""summarize_rm_rule.py -- per-year / per-session breakdown of the graduated rule.

Reads the per-trade output of `event_bt/bt.py run` (trades.csv) for the T-14
and T-7 entries on the liquid universe, applies the pre-registered
realized-move cheapness rule (ratio_avg_rm <= 0.90), and writes small summary
tables plus a per-year figure. The per-trade files are NOT published (they are
derived from licensed OPRA quotes); this script is how the published
summaries in results/liquid_2020_2026/ were produced.

Usage:
  python scripts/summarize_rm_rule.py \
      --t14 event_bt/results_liquid_full/T14/trades.csv \
      --t7  event_bt/results_liquid_full/T7/trades.csv \
      --out results/liquid_2020_2026 --fig figures/rm_rule_by_year.png
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

RULE = 0.90  # ratio_avg_rm <= 0.90, fixed before the liquid run


def rule_trades(path: str) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["ann_date"])
    d = d[d["ratio_avg_rm"] <= RULE].copy()
    d["year"] = d["ann_date"].dt.year
    return d


def table(d: pd.DataFrame, by: str) -> pd.DataFrame:
    g = d.groupby(by)["long_ret_net"]
    return pd.DataFrame({"n": g.size(), "mean_net": g.mean(),
                         "median_net": g.median(),
                         "win_rate": g.apply(lambda s: float((s > 0).mean()))})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t14", required=True)
    ap.add_argument("--t7", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fig", default=None)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rows = []
    for lead, path in (("T14", a.t14), ("T7", a.t7)):
        d = rule_trades(path)
        for by in ("year", "session"):
            t = table(d, by).reset_index()
            t.insert(0, "entry", lead)
            t.round(4).to_csv(os.path.join(a.out, lead, "rm_rule_by_%s.csv" % by),
                              index=False)
        yt = table(d, "year")
        yt["entry"] = lead
        rows.append(yt)
        print("%s rm-rule: n=%d mean net %+.2f%%, positive years %d/%d"
              % (lead, len(d), 100 * d["long_ret_net"].mean(),
                 int((yt["mean_net"] > 0).sum()), len(yt)))

    if a.fig:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        both = pd.concat(rows).reset_index()
        years = sorted(both["year"].unique())
        x = np.arange(len(years))
        w = 0.38
        ink, muted, grid = "#1f1f1e", "#6b6a64", "#e4e3dd"
        fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
        fig.patch.set_facecolor("#fcfcfb")
        ax.set_facecolor("#fcfcfb")
        series = (("T14", "#2a78d6", "Entry T-14 (graduated)"),
                  ("T7", "#eb6834", "Entry T-7 (same rule)"))
        for i, (lead, color, label) in enumerate(series):
            s = both[both["entry"] == lead].set_index("year").reindex(years)
            vals = 100 * s["mean_net"].values
            bars = ax.bar(x + (i - 0.5) * (w + 0.02), vals, w, color=color,
                          label=label, zorder=3)
            if lead == "T14":
                for b, v, n in zip(bars, vals, s["n"].values):
                    ax.annotate("%+.1f%%\nn=%d" % (v, n),
                                (b.get_x() + b.get_width() / 2, v),
                                xytext=(0, 3 if v >= 0 else -22),
                                textcoords="offset points", ha="center",
                                fontsize=7, color=muted)
        ax.axhline(0, color=muted, lw=0.8, zorder=2)
        ax.set_xticks(x, [str(y) for y in years], color=ink)
        ax.set_ylabel("mean net return per trade (%)", color=ink)
        ax.set_title("Cheap-vs-realized-history long straddle, liquid names, "
                     "net of costs", color=ink, fontsize=10, loc="left", pad=22)
        ax.grid(axis="y", color=grid, lw=0.6, zorder=0)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(grid)
        ax.tick_params(colors=muted)
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo * 1.15, hi * 1.15)
        ax.legend(frameon=False, fontsize=8, loc="lower left", ncol=2,
                  bbox_to_anchor=(0, 1.0))
        fig.tight_layout()
        os.makedirs(os.path.dirname(a.fig) or ".", exist_ok=True)
        fig.savefig(a.fig, facecolor=fig.get_facecolor())
        print("wrote", a.fig)


if __name__ == "__main__":
    main()
