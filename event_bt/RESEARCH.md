# Pre-Earnings Event-Vol: Deep Research + the Revised Idea (2026-08-16)

*Deep-dive follow-up to `VOLATILITY_VIBES_CHANNEL.md` Strategy 1 (video #6: long
ATM straddle at T-14, exit just before the announcement). Three research
threads were run 2026-08-16: academic literature, practitioner evidence, and
data vendors (vendor results live in `DATA_SPEC.md`). This doc consolidates
what's known and defines the revised, testable idea the `event_bt` harness
implements.*

---

## 1. Where the idea stands after our own math

`scripts/verify_vv_math.py` (2026-08-12) proved: with ambient vol fairly priced and no
event repricing, the T-14 → T-0 long straddle is **exactly zero-EV before
costs** — the event variance you bought is still in the exit price. So the
whole P&L decomposes as:

```
EV = E[event-vol repricing] + (ambient realized − ambient implied) − costs
```

The "IV ramp" is mechanical and monetizes nothing. Any real edge must come from
the **event-variance component itself getting repriced upward during the hold**,
and/or ambient RV > IV. That's the discrepancy to hunt.

## 2. What the academic record says (thread 1)

**The only published positive pre-event result is short-window, not T-14.**
Gao–Xing–Zhang (JFQA 2018; 1996–2013, ~77k straddles, midpoint prices, no
spreads paid): delta-neutral straddles earn **+1.9–2.6% over T-3 → T-1**
(t≈16), the single biggest day being T-2 → T-1; through-event windows die under
dollar-open-interest weighting (−0.67% for [−3,+1]). Returns concentrate in
small, high-vol, wide-spread, low-option-volume names — the biggest returns
live exactly where they can't be filled. **No academic paper tests entries
earlier than T-3.** The 9 extra days of a T-14 entry pay the single-name
ambient vol premium GXZ themselves price at ≈ **−2%/week** — so the
unconditional T-14 entry is negative-EV before costs per the literature, not
zero. Khan & Khan (SSRN 2024, 17y of S&P 500 events) confirm: straddles bought
T-30 bleed into T-1 on average.

**Through the event, the average discrepancy favors sellers, modestly.**
Dubinsky–Johannes–Kaeck–Seeger (RFS 2019, 2000–2015): implied earnings-day vol
8.22% vs realized 7.42% (~80bp premium); T-1 → T+1 straddles average −8%
(median −10%). Alexiou et al. (Rev. Fin. 2025, 2013–2020 weeklies): mean −0.9%,
median −15.4% through the event; names with *concave* pre-event IV curves
(visibly priced binary risk) lose −3.7% vs +0.9% for non-concave — differences
survive 50–75%-of-spread cost assumptions.

**The repricing channel itself is an open research gap.** No published paper
measures the T-14 → T-0 *path* of the implied earnings move or tests
convergence to the name's own historical norm. Closest evidence, all indirect
but all pointing the same way: DJKS show terminal (T-1) event vol is
well-calibrated to firm history (~85% cross-sectional correlation with realized
announcement vol) — so if T-14 event vol is below the name's norm and T-1
pricing is calibrated, *arithmetic implies the repricing*; GXZ's day-by-day
returns show event variance still being added late, concentrated in noisy
names; Chen–Gan–Vasquez (JBF 2023) show the straddle's jump-component share
rises sharply pre-EAD. **VV's specific claim occupies a genuine hole in the
literature — which cuts both ways: nobody has confirmed it, nobody has killed
it.**

**Costs are the deciding variable, and execution is the strategy.** Muravyev &
Pearson (RFS 2020): traders who time executions pay <40% of conventional
effective spreads — vol-value strategies flip from unprofitable to viable on
execution alone. de Silva–Smith–So (Rev. Fin. 2025): retail spreads average
~20% of option price and *widen* into high-expected-vol events; retail loses
5–9% per announcement episode. BSIC's GXZ replication (S&P 500 names,
2011–2021): **+1.17% gross → −9.07% net** paying full spreads. Duarte et al.
(RFS 2026): standard option-return data filters alone can inflate Sharpes 10x —
midpoint event returns in wide-spread names are exactly the fragile object.

## 3. What practitioners say (thread 3)

- **No independent replication of VV's backtests exists anywhere** (Reddit, X,
  Elite Trader, blogs — the record is empty, for and against). His "Forward
  Factor" calendar is repackaged Predicting Alpha / Sinclair material from
  2022-23. oquants ($297/qtr) shows no live track record; its own backtester
  can't even express the exit-before-earnings rule (holds to expiration), and
  it sells *both* a long and a short pre-earnings vol product simultaneously.
- **The one long-running live log of this exact trade**: SteadyOptions has
  bought pre-earnings straddles (enter 2–15d before, exit pre-event) since
  ~2012, self-reporting ~70% win years and 5–10% per-trade targets — the
  existence proof that careful name selection + patient fills can keep this
  positive, at boutique size.
- **The sell side is the crowded, tooling-supported retail trade** (tastylive
  doctrine, Predicting Alpha's published live log of $225k over 1,381 short
  trades conditioned on implied ≫ historical). The cheap-vs-history filter is
  well-documented **on the short side**; its long-side mirror is plausible and
  essentially untested publicly at the 14-day horizon.
- **Regime note**: ORATS (Feb 2026) reports realized earnings moves beating
  implied for multiple recent seasons — straddle buyers averaged ~+45% this
  season vs a 12-quarter average of ~−2%. The long side is being marketed (by
  VV among others) exactly when the short side has been bleeding. Crowding on
  the long-early side: low.

## 4. The revised idea

The VV trade as stated (unconditional-ish long at T-14, linear model, his
data) is not the trade. The research says the discrepancy — if it exists — is
**a relative-value repricing effect with a time-of-arrival structure**, and it
should be attacked as such:

1. **Trade the signal, not the structure.** The tradeable object is *event
   variance mispriced vs the name's own history*, extracted term-structure
   style (DJKS), not raw IV. Cheap → own it into the event; rich → be short
   through the event (the side with the stronger academic record). One signal,
   two exits — the RV book.
2. **Entry timing is an empirical parameter, not T-14 dogma.** Literature says
   the documented pre-event return lives in T-3 → T-1; every day earlier adds
   ~−0.3%/day of ambient vol premium unless the ambient leg is also cheap.
   The harness sweeps T-14 / T-7 / T-3 and reports where (if anywhere) the
   filtered edge peaks. A T-3 entry also shrinks the cost base (2 fewer weeks
   of spread exposure per unit of event vega? No — same round-trip, but far
   less ambient bleed and capital time).
3. **Delta-hedge to isolate the bet.** GXZ's result is for delta-neutral
   straddles; unhedged P&L is mostly gamma luck. The harness computes both;
   the hedged number is the thesis test, the unhedged number is the practical
   retail implementation.
4. **Execution IS the edge budget.** Mid-or-better patient fills (φ ≤ 0.5) or
   nothing; the harness prices every trade at φ ∈ {0, 0.5, 1} so the
   edge-vs-friction frontier is explicit. If it only works at φ=0, it's a
   market-maker's trade, not ours.
5. **Kill criteria are pre-registered** (§5). No threshold tuning on the full
   sample — fixed rules stated now, walk-forward for anything fitted.

## 5. Pre-registered hypotheses (what the data will decide)

| # | Hypothesis | Test | Kill if |
|---|---|---|---|
| H1 | Implied earnings move mean-reverts toward the name's own history from T-14 to T-0 | `cores`/`repricing`: slope of Δlog(IM) on log(IM/own-avg), per-year | slope ≥ 0 or unstable sign across years |
| H2 | Cheap-quintile events reprice UP (not just rich ones down) | cheapest-quintile mean Δlog(IM) | ≤ 0 — then "cheapness" is just measurement noise and the long side has nothing |
| H3 | Conditioned long straddle (ratio_avg ≤ 0.9) is positive net at φ=0.5 at SOME entry in {14,7,3} | replicate + sweep | max over entries ≤ 0 net |
| H4 | The delta-hedged version retains ≥ half the unhedged filtered edge | dh columns | dh ≈ 0 while unhedged > 0 (edge was gamma luck / regime beta) |
| H5 | The two-sided RV book beats either leg alone risk-adjusted | rvbook Sharpe-like vs legs | book ≤ best single leg |

Priors (honest): H1 likely holds weakly (attenuated by measurement noise);
H2 is the real coin-flip — the literature's calibration evidence implies it,
but selection on a noisy signal argues regression-to-mean will eat most of it;
H3 at T-3 more likely than at T-14; expect VV's +3.3% to shrink to ~0–1.5%
net in liquid names, tail-driven. The short side (H5's other leg) is the
better-documented half and rescues the project even if H3 dies.

## 6. What's already running / next actions

- `event_vol.py snapshot` keeps accumulating the live implied-move history
  (Tier 0, free, not backfillable — keep running it weekly).
- Harness `event_bt/` selftest-verified 2026-08-16 (all 6 checks PASS).
- Next action: **Tier 1 ORATS purchase ($99, one month)** → `bt.py cores`
  answers H1/H2 on 2007→present real data. Only if H2 survives, spend the
  ~$599 on bulk strikes for H3–H5.

## Sources (key)

Gao, Xing & Zhang JFQA 53(6) 2018 (SSRN 2204549) · Dubinsky, Johannes, Kaeck &
Seeger RFS 32(2) 2019 · Goyal & Saretto JFE 94 2009 · Vasquez JFQA 52(6) 2017 ·
Muravyev & Pearson RFS 33(11) 2020 · Smith & So JAR 60(2) 2022 · Chen, Gan &
Vasquez JBF 149 2023 · Alexiou, Goyal, Kostakis & Rompolis Rev. Fin. 29(4)
2025 · de Silva, Smith & So Rev. Fin. 2025 (SSRN 4050165) · Bali et al. RFS
36(9) 2023 · Duarte et al. SSRN 4590083 · Khan & Khan SSRN 4832160 · Lipkin et
al. J. Risk 2024 · BSIC "Straddling into earnings" I/II (2022) · SteadyOptions
trade logs · ORATS blog (2021 backtest; Feb 2026 season report) · Moontower
"Earnings IV Glide Path". Flags: Khan & Khan, Duarte et al., and the GXZ
working-paper cost tables were read via summaries/snippets, not full texts;
VV's own numbers remain unverified by anyone.
