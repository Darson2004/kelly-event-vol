#!/usr/bin/env python
"""bt.py -- CLI for the event-vol backtest harness (event_bt).

Workflow when vendor data arrives (see DATA_SPEC.md for what to buy):

  1. python bt.py ingest --raw "raw/*.csv" --events-file earnings.csv
                         [--vendor orats] [--map map.json]
  2. python bt.py validate                 # coverage + skip-reason report
  3. python bt.py run                      # all three analyses -> results/

Before any data exists:

  python bt.py selftest                    # synthetic world, end-to-end check

Run:
  python bt.py ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import engine  # noqa: E402


def _fmt_stats(s: dict, label: str) -> str:
    if not s or s.get("n", 0) == 0:
        return "  %-28s (no trades)" % label
    base = ("  %-28s n=%-5d mean %+7.2f%%  med %+7.2f%%  win %4.0f%%  t=%+5.1f"
            % (label, s["n"], 100 * s["mean"], 100 * s["median"],
               100 * s["win"], s.get("t", float("nan"))))
    kf = s.get("kelly_f")
    if kf is not None and kf == kf:  # not NaN
        base += "  Kelly f*=%.2f%s" % (kf, " (VETO)" if kf == 0 else "")
    return base


def print_summary(summary: dict) -> None:
    print("=" * 74)
    print("EVENT-VOL BACKTEST  --  %d events, %d usable trades, %s tickers"
          % (summary["n_events"], summary["n_usable"],
             summary["coverage"]["tickers"]))
    cov = summary["coverage"]
    print("span %s .. %s | with implied-move history: %d | median entry spread %.1f%% of premium"
          % (cov["first"], cov["last"], cov["with_im_history"],
             100 * (cov["median_spread_frac"] or 0)))
    if summary.get("skip_reasons"):
        print("skips: %s" % summary["skip_reasons"])
        miss = summary["skip_reasons"].get(
            "missing straddle quote at entry or exit", 0)
        if miss > 0.05 * max(summary["n_events"], 1):
            print("  WARNING: %d events (%.0f%%) dropped for missing quotes. "
                  "If those are the big movers, long-straddle stats are "
                  "biased DOWN -- widen the strike band at ingest."
                  % (miss, 100 * miss / summary["n_events"]))
    if "error" in summary:
        print("ERROR: %s" % summary["error"])
        return

    r = summary.get("repricing")
    if r:
        print("-" * 74)
        print("1. REPRICING CHANNEL (does cheap event vol get bid into the event?)")
        if "slope" in r:
            print("  slope d_log_im ~ log(ratio_avg_im): %+.3f (t=%+.1f)  "
                  "[negative = mean reversion = the edge exists]"
                  % (r["slope"], r["slope_t"]))
            print("  mean repricing: all %+.3f | cheapest quintile %+.3f | "
                  "richest quintile %+.3f"
                  % (r["mean_repricing_all"], r["mean_repricing_cheapest_q"],
                     r["mean_repricing_richest_q"]))
        else:
            print("  %s" % r.get("note"))

    rep = summary.get("replicate")
    if rep:
        print("-" * 74)
        print("2. REPLICATE VV #6 (long straddle T-14 -> T-0, real spreads)")
        print(_fmt_stats(rep["unconditional_gross"], "unconditional gross"))
        print(_fmt_stats(rep["unconditional_net"], "unconditional net"))
        print(_fmt_stats(rep["unconditional_dh_net"], "unconditional net (d-hedged)"))
        print(_fmt_stats(rep["fixed_rule"]["gross"],
                         "cheap rule (im hist) gross"))
        print(_fmt_stats(rep["fixed_rule"]["net"], "cheap rule (im hist) net"))
        print(_fmt_stats(rep["fixed_rule"]["dh_net"],
                         "cheap rule net (d-hedged)"))
        print(_fmt_stats(rep["fixed_rule"].get("leg_dh_net", {}),
                         "cheap rule net (1-leg dh)"))
        print(_fmt_stats(rep["fixed_rule_rm"]["net"], "cheap rule (rm hist) net"))
        wf = rep["walkforward"]
        print(_fmt_stats(wf.get("net", {}), "walk-forward OLS net")
              + ("   (selected %d of %d OOS)" % (wf["n_selected"], wf["n_oos"])))

    rv = summary.get("rvbook")
    if rv:
        print("-" * 74)
        print("3. RV BOOK (long cheap T-14->T-0 / short rich T-0->T+1)")
        print(_fmt_stats(rv["long"]["net"], "long leg net"))
        print(_fmt_stats(rv["short"]["net"], "short leg net"))
        b = rv.get("book")
        if b:
            print("  book @ f=%.0f%%: %d trades, CAGR %+.1f%%, maxDD %.1f%%, "
                  "Sharpe-like %.2f"
                  % (100 * b["f"], b["n_trades"], 100 * b["cagr"],
                     100 * b["max_dd"], b["sharpe_like"]))
    print("=" * 74)


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------

def cmd_selftest(args) -> None:
    import synth
    data_dir = os.path.join(HERE, "_synth")
    out_dir = os.path.join(data_dir, "results")
    print("generating synthetic world -> %s" % data_dir)
    truth = synth.generate(data_dir, n_tickers=args.tickers,
                           n_quarters=args.quarters)
    summary = engine.run_all(data_dir, out_dir, phi=0.5)
    print_summary(summary)

    import pandas as pd
    trades = pd.read_csv(os.path.join(out_dir, "trades.csv"),
                         parse_dates=["ann_date"])
    tru = pd.DataFrame(truth["per_event"])
    tru["ann_date"] = pd.to_datetime(tru["ann"])
    m = trades.merge(tru, left_on=["ticker", "ann_date"],
                     right_on=["ticker", "ann_date"], how="inner")
    rel_err = (m["im_entry"] / m["im0"] - 1).abs().median()

    checks = []

    def chk(name, cond, detail):
        checks.append((name, bool(cond), detail))

    chk("implied-move recovery", rel_err < 0.15,
        "median |im_entry/planted - 1| = %.3f (< 0.15)" % rel_err)
    r = summary["repricing"]
    chk("repricing slope negative", r["slope"] < -0.2 and r["slope_t"] < -4,
        "slope %+.3f t %+.1f (planted kappa=%.1f)" %
        (r["slope"], r["slope_t"], truth["kappa"]))
    unc = summary["replicate"]["unconditional_gross"]
    chk("unconditional ~ zero-EV gross", abs(unc["mean"]) < 0.03,
        "mean %+.3f (|.| < 0.03)" % unc["mean"])
    ch = summary["replicate"]["fixed_rule"]["gross"]
    chk("cheap filter beats unconditional (gross)",
        ch.get("n", 0) > 30 and ch["mean"] > unc["mean"] + 0.015,
        "cheap %+.3f vs unconditional %+.3f (n=%d)"
        % (ch.get("mean", float("nan")), unc["mean"], ch.get("n", 0)))
    chn = summary["replicate"]["fixed_rule"]["net"]
    chk("costs bite (net < gross)", chn["mean"] < ch["mean"],
        "net %+.3f < gross %+.3f" % (chn["mean"], ch["mean"]))
    sh = summary["rvbook"]["short"]["gross"]
    chk("short side captures planted event VRP", sh.get("n", 0) > 10
        and sh["mean"] > 0.0,
        "short gross mean %+.3f (n=%d)" % (sh.get("mean", float("nan")),
                                           sh.get("n", 0)))

    print()
    ok = True
    for name, passed, detail in checks:
        print("  [%s] %-42s %s" % ("PASS" if passed else "FAIL", name, detail))
        ok &= passed
    print()
    if not ok:
        raise SystemExit("SELFTEST FAILED")
    print("SELFTEST PASSED -- pipeline verified end-to-end; drop real data in "
          "and run `bt.py ingest` / `bt.py run`.")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def cmd_validate(args) -> None:
    import pandas as pd
    events, chains, _ = engine.load_canonical(args.data)
    recs = engine.build_event_records(events, chains,
                                      entry_target=args.entry_target)
    rows = [{"ticker": r.ticker, "ann_date": r.ann_date,
             "status": r.skip_reason or "OK",
             "entry_date": r.entry_date, "exit_date": r.exit_date,
             "expiry_post": r.expiry_post,
             "has_pre_expiry": r.expiry_pre is not None,
             "n_marks": len(r.marks), "n_im_path": len(r.im_path)}
            for r in recs]
    df = pd.DataFrame(rows)
    path = os.path.join(args.data, "validation.csv")
    df.to_csv(path, index=False)
    n_ok = int((df["status"] == "OK").sum())
    print("events: %d | usable: %d (%.0f%%)" %
          (len(df), n_ok, 100 * n_ok / max(len(df), 1)))
    bad = df[df["status"] != "OK"]["status"].value_counts()
    if len(bad):
        print("skip reasons:")
        for k, v in bad.items():
            print("  %-45s %d" % (k, v))
    ok = df[df["status"] == "OK"]
    if len(ok):
        print("usable events: pre-event expiry available for %.0f%% "
              "(needed for clean ambient IV + calendars)"
              % (100 * ok["has_pre_expiry"].mean()))
        print("median obs days per event: %.0f (>= 10 enables daily "
              "repricing-path analysis)" % ok["n_marks"].median())
    print("per-event detail -> %s" % path)


def cmd_cores(args) -> None:
    """Repricing-channel analysis from an implied-earnings-move history alone
    (ORATS hist/cores). The cheapest possible test of the thesis: no chains."""
    import pandas as pd
    from ingest import load_events, _match_cols
    raw = pd.read_csv(args.cores)
    m = _match_cols(raw, {
        "obs_date": ["tradedate", "trade_date", "obs_date", "date"],
        "ticker": ["ticker", "symbol"],
        "im": ["impliedearningsmove", "implied_earnings_move", "im",
               "implied_move", "impliedmove"],
    }, "cores")
    cores = pd.DataFrame({k: raw[v] for k, v in m.items()})
    cores["obs_date"] = pd.to_datetime(cores["obs_date"]).dt.date
    cores["ticker"] = cores["ticker"].astype(str).str.upper()
    cores["im"] = pd.to_numeric(cores["im"], errors="coerce")
    events = load_events(args.events_file)

    df = engine.build_cores_table(cores, events,
                                  entry_target=args.entry_target)
    os.makedirs(args.out, exist_ok=True)
    df.to_csv(os.path.join(args.out, "cores_events.csv"), index=False)
    print("cores-only event table: %d events, %d with history"
          % (len(df), int(df["ratio_avg_im"].notna().sum())))
    r = engine.analysis_repricing(df, args.out)
    if "slope" in r:
        print("REPRICING: slope %+.3f (t=%+.1f) | mean d_log_im all %+.3f | "
              "cheapest quintile %+.3f | richest %+.3f"
              % (r["slope"], r["slope_t"], r["mean_repricing_all"],
                 r["mean_repricing_cheapest_q"], r["mean_repricing_richest_q"]))
        print("negative slope + positive cheap-quintile repricing = the "
              "long-side channel exists; tables -> %s" % args.out)
    else:
        print(r.get("note"))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("selftest", help="synthetic end-to-end verification")
    s.add_argument("--tickers", type=int, default=30)
    s.add_argument("--quarters", type=int, default=22)
    s.set_defaults(func=cmd_selftest)

    g = sub.add_parser("ingest", help="normalize vendor files -> canonical")
    g.add_argument("--raw", required=True,
                   help="file, dir, or glob of vendor chain CSVs")
    g.add_argument("--events-file", required=True,
                   help="earnings dates CSV (ticker, date, session)")
    g.add_argument("--vendor", default="orats", choices=["orats", "generic"])
    g.add_argument("--map", dest="colmap", default=None,
                   help="JSON column map for generic vendors")
    g.add_argument("--out", default=os.path.join(HERE, "data", "canonical"))
    g.set_defaults(func=lambda a: __import__("ingest").run_ingest(
        a.raw, a.vendor, a.events_file, a.out, a.colmap))

    v = sub.add_parser("validate", help="coverage report on canonical data")
    v.add_argument("--data", default=os.path.join(HERE, "data", "canonical"))
    v.add_argument("--entry-target", type=int, default=14)
    v.set_defaults(func=cmd_validate)

    c = sub.add_parser("cores", help="repricing analysis from implied-move "
                                     "history alone (no chains needed)")
    c.add_argument("--cores", required=True,
                   help="CSV with tradeDate,ticker,impliedEarningsMove")
    c.add_argument("--events-file", required=True)
    c.add_argument("--entry-target", type=int, default=14)
    c.add_argument("--out", default=os.path.join(HERE, "results", "cores"))
    c.set_defaults(func=cmd_cores)

    r = sub.add_parser("run", help="run the analyses")
    r.add_argument("--data", default=os.path.join(HERE, "data", "canonical"))
    r.add_argument("--out", default=os.path.join(HERE, "results"))
    r.add_argument("--phi", type=float, default=0.5,
                   help="fraction of half-spread paid per fill (0=mid, 1=full)")
    r.add_argument("--commission", type=float, default=0.75,
                   help="$ per contract per side")
    r.add_argument("--entry-target", default="14",
                   help="calendar days before earnings; comma list sweeps "
                        "(e.g. 14,7,3 -- lit says the edge lives near T-3)")
    r.add_argument("--which", default="all",
                   choices=["all", "repricing", "replicate", "rvbook"])
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    args.func(args)


def cmd_run(a):
    targets = [int(x) for x in str(a.entry_target).split(",")]
    if len(targets) == 1:
        print_summary(engine.run_all(a.data, a.out, phi=a.phi,
                                     commission=a.commission,
                                     entry_target=targets[0], which=a.which))
        return
    rows = []
    for t in targets:
        out_t = os.path.join(a.out, "T%d" % t)
        s = engine.run_all(a.data, out_t, phi=a.phi, commission=a.commission,
                           entry_target=t, which=a.which)
        print_summary(s)
        rows.append((t, s))
    print()
    print("ENTRY-TIMING SWEEP (long straddle, exit T-0)")
    print("%-8s %-6s %-22s %-22s %-22s" % ("entry", "n", "uncond net",
                                           "cheap-rule net", "cheap d-hedged net"))
    for t, s in rows:
        rep = s.get("replicate", {})

        def _m(st):
            return ("%+.2f%% (win %.0f%%)" % (100 * st["mean"], 100 * st["win"])
                    if st and st.get("n") else "--")
        print("%-8s %-6s %-22s %-22s %-22s"
              % ("T-%d" % t, s.get("n_usable", 0),
                 _m(rep.get("unconditional_net")),
                 _m((rep.get("fixed_rule") or {}).get("net")),
                 _m((rep.get("fixed_rule") or {}).get("dh_net"))))


if __name__ == "__main__":
    main()
