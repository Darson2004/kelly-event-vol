# Execution Policy — v2

The live execution policy for the pre-earnings long straddle. Every rule
carries its evidence grade. The execution-research loop edits this file and only
this file when a rule graduates or is demoted.

**v2 is the first version where the cost model rests on measured fills**
($52.65 of OPRA `tcbbo`, 539 entry days, 2023Q2–2026Q3). The headline is
counter-intuitive: the inherited number survives, the inherited *language*
does not.

| # | Rule | Grade | Basis |
|---|---|---|---|
| P1 | Enter at T−14 | **MEASURED-ON-COST** | T−14 is the most expensive of five leads: paired penalty 17.7bp vs T−3 (CI [12.8, 22.5], 967 pairs, E0004), 23.9bp strict. Not a reason to move — see v1 hurdle caveat. |
| P2 | **Cost model: φ ≈ 0.5 of the quoted half-spread per crossing (round trip ≈ 1.0)** | **MEASURED-WITH-BAND** | The number is retained; its *basis* changes from inherited to evidence-backed. Defensible entry-leg planning band **0.40–0.55, point ~0.47**; round trip φₑ+φₓ ∈ **[0.8, 1.2]** vs incumbent 1.0. See the band table below. |
| P2a | **"Mid-or-better fills only" — WITHDRAWN** | **REFUTED** | Only **7.7%** of volume prints at mid (CI [5.9, 9.3]); just 9.5% of events see half their volume there. The language was never achievable. |
| P2b | **φ is not a constant: it falls with quoted width and rises with clip size** | **MEASURED** | By tick width: 1-tick 0.889 → >8-tick 0.389 (17,194 prints). By clip: ≥1 lot 0.403 → ≥10 lots 0.473 → ≥25 lots 0.509. |
| P3 | Exit before the print | **BACKTESTED** | graduated result is built on pre-print exits |
| P4 | 1–3% premium per name, quarter-Kelly ceiling, f/N concurrent | **BACKTESTED** | Kelly f\*=0.81 on n=193; quarter-Kelly is doctrine |
| P5 | Liquid universe only (42 names) | **BACKTESTED** | small/mid-caps: spread 3× edge at every depth |
| P6 | No pre-trade executability screen | **DEFAULT** | untested; EX-1/EX-4 gated on EX-6 |
| P7 | Do NOT move the entry to T−10 | **REFUTED** | day-of-week artifact; weekday-adjusted p=0.771 |
| P8 | **No capacity/abort rule may be written yet** | **BLOCKED** | The obvious rule ("abort if clip > x% of daily volume") cannot be written: our volume figures are **15:00–16:00 ET only**, not daily (ANOM-8). Denominator must be re-derived first. |

## The φ band, and why the incumbent number survived

| basis | entry-leg φ |
|---|---|
| statistical CI at the measured 1-lot margin | 0.375 – 0.416 |
| + weighting / aggregation convention | 0.34 – 0.44 |
| + spread regime (2023-25 tight vs 2026 wide) | 0.24 – 0.46 |
| + clip size 1 → 25 contracts | up to 0.51 – 0.64 |
| **planning band** | **0.40 – 0.55, point ~0.47** |

A naive read of the raw measurement gives φ=0.40 and a restated edge of
+6.62%/trade. **Do not use 0.40.** It is the price paid by the marginal
~1.25-lot order, in the tight 2023–25 regime, on the entry leg only,
conditional on a print having occurred at all. Three corrections push it up,
and together they bracket the incumbent 0.5:

1. **Size.** The strategy does not trade 1-lots. At ≥10 contracts φ_B = 0.473
   (CI contains 0.50); at ≥25 it is 0.509. At a $15.25 median straddle, 25
   contracts ≈ $38k premium — the operative clip for any book above ~$1.3M.
2. **Regime.** Median entry cost ran 1.0–1.45% through 2025Q3 and then
   **2.28 → 2.94%** across 2025Q4–2026Q3 — real widening, confirmed on the
   tape independently of the panel. φ_B trends with it (Spearman −0.106,
   p=0.014; 2026Q3 = 0.235). A single constant is the wrong model.
3. **Convention.** φ is not one number. Median 0.395 vs mean 0.439 vs
   dollar-aggregate 0.345. Portfolio drag is a mean, not a median.

**Exit leg is UNMEASURED and it is half the claim.** The restatement turns
negative at φ_exit = 0.605 — not a remote value, since φ rises in the final
five minutes (0.468), rises with size, and the exit is a crowded pre-print
sell at elevated IV.

## What the fill data actually taught us

**φ is largely a tick-grid phenomenon, not a negotiation phenomenon.** In a
one-tick-wide market there is no attainable price strictly inside the touch,
so φ is pinned near 1 by arithmetic (0.889 measured); where the grid offers
13 interior points φ falls to 0.389. The apparent "wide markets fill better"
result is this, not skilled execution. Practical consequence: **tick width,
not spread width, is the executability variable to screen on.**

**Trade-moment selection is real.** On liquid actively-traded events the
near-close mark is essentially unbiased (tape/panel 0.954); on quiet names it
reads 0.867 because the only prints are moments a maker briefly tightened —
a state we cannot summon on demand.

## Evidence grades

- **POLICY** — audited, cleared alpha, confirmed prospectively on a season
  that did not exist at registration.
- **MEASURED-WITH-BAND** — measured and audited, but the honest output is an
  interval whose width is driven by choices (size, regime, convention), not
  by sampling error.
- **MEASURED / MEASURED-ON-COST** — measured and audited on one side only.
- **BACKTESTED** — supported by the graduated backtest, not by this pack.
- **ASSUMED** — inherited, untested. **REFUTED** — tested and rejected.
- **DEFAULT** — absence of a rule, recorded so it is deliberate.
- **BLOCKED** — cannot be written until a stated prerequisite is met.

## Standing limitations

1. Every panel mark is a **near-close quote**; the fill data is **15:00–16:00
   ET only**. Nothing here describes the open, midday, or a full session.
2. **Entry weekday is near-collinear with lead bucket** — hold announcement
   weekday fixed in any lead comparison or P7's artifact returns.
3. Within an event, `dte_true = lead + constant`, so "closer to the print"
   and "closer to expiry" are only partly separable.
4. Staleness is measured, not assumed: 3.47% of entries have ≥1 stale leg,
   0.65% are economically stale. Whether that costs anything is EX-3.
5. **Fill coverage is 2023Q2+ only** — 0 of the 397 pre-2023 events. Pre-2023
   markets were measurably wider (cost 1.62% vs 1.33%).
6. **The aggregation used to build the fills panel is internally
   inconsistent** (`exec_harness.py:707-708` averages per-leg ratios while
   `cost_frac` is a ratio of sums). φ_B is robust to this — the two errors
   cancel — but φ_A is not, and the dollar-correct φ_A is 0.478 with a CI
   that contains 0.50. Scheduled for amendment A4.

## Change log

- **v2 — 2026-09-01 (tick 2).** P2 regraded ASSUMED → MEASURED-WITH-BAND;
  number retained, basis replaced, band published. P2a added (mid-or-better
  REFUTED). P2b added (φ falls with tick width, rises with clip size). P8
  added (capacity rule blocked on a bad denominator). Limitations 5–6 added.
  Audit: `notes/P2_audit.md`, verdict FRAGILE.
- **v1.1 — 2026-09-01.** Staleness measured; P2 basis noted as purchasable.
- **v1 — 2026-09-01 (tick 1).** P1 regraded; P7 added; convexity withdrawn.
- **v0 — 2026-09-01.** Baseline; no rules validated.
