# P2 AUDIT — VERDICT: FRAGILE

Filed by the orchestrator on the auditor's behalf (Write was disabled in its
session). Replays logged E0071–E0090 under `hyp=P2-AUDIT`. Panel hash
`a4340d0f22dcd3c6…` verified. No pack file modified by the auditor.

## Replay: YES — 17/17 exact

E0054 −0.12202 · E0055 +0.58992 · E0056 −0.07283 · E0057 +0.17983 ·
E0058 +0.82877 · E0059 −0.20862 · E0060 −0.44407 · E0070 +0.21728; every
`admit` count / cost-median / tail-rate / perm-p identical. All ~12 unlogged
AUDIT-DIAGNOSTIC numbers also reproduce to 4dp. **NOT FABRICATED.**
Three cosmetic slips: `touch_sz` median 81.0 not 79.6; "12 of 14 seasons in
[0.49,0.61]" is 11 of 14; usable pairs 539 not 537.

A3 mid-audit change acknowledged: all point estimates replay bit-identically,
so A3 changed reporting, not statistics.

## New under A3
E0054 `perm_p` = **0.02398 — does NOT clear alpha_2 = 0.015198.**
E0057/E0059/E0070 sit at the permutation floor 0.001. Bonferroni-17 on the
floor reads = 0.017, marginally failing. Calibrated BF10 ≤ 4.11 at E0054,
posterior odds 0.46:1 — still against. "Promote nothing" is correct.

## KV1 (crux) — THE STORY IS WRONG, THE NUMBER SURVIVES

Stated arithmetic does not compute: 0.55 × 0.88 = **0.484**, not 0.396.
median(phi_B/phi_A) = **0.7796** — a 22% discount, not 12%. The published
mechanism explains barely half the gap it is invoked for.

**Root cause — aggregation mismatch** (`exec_harness.py:707-708`):
`eff_half_frac`/`quoted_half_frac` are `g.sum()/n_legs`, a MEAN OF PER-LEG
RATIOS, while `cost_frac` (line 376) is `spread/(2*mid)`, a RATIO OF STRADDLE
SUMS; `phi_implied` is a third thing (VW mean of per-trade ratios,
equal-weighting contracts regardless of dollars at stake).

Recomputed from the raw tape in consistent dollars (963 leg-days):

| | panel | dollar-correct |
|---|---|---|
| phi_A | 0.5495 [0.5247, 0.5800] | **0.4777 [0.4564, 0.5089]** ← CI CONTAINS 0.50 |
| phi_B | 0.3964 [0.3749, 0.4160] | **0.3951 [0.3762, 0.4137]** ← robust |

phi_B survives (the two errors cancel). phi_A does not: "0.5 is too kind" was
an artifact of equal-contract ratio-averaging.

**The 12% level gap is TRADE-MOMENT SELECTION, not mark drift.** The whole
purchase is 15:00–16:00 ET and the 15:44–47 panel mark sits inside that hour;
VW quoted half is flat across it. Composition:

| | n | tape/panel half | median last-hr volume |
|---|---|---|---|
| both legs print at 15:44–47 | 97 | 0.954 | 193 |
| they do not | 327 | 0.867 | 36 |

By cost quintile: 0.971 / 0.911 / 0.857 / 0.803 / 0.774. The near-close mark
is essentially unbiased on liquid, actively-traded events; the discount lives
in quiet wide names where the only prints are moments a maker briefly
tightened.

## KV2 volume weighting — FAILS TO KILL

| | phi_A (dollar) | phi_B (dollar) |
|---|---|---|
| volume-weighted | 0.4777 | 0.3951 |
| per-trade equal weight | 0.4600 | 0.3979 |
| drop largest print decile | 0.4525 | 0.3853 |

69.4% of volume is in ≥10-lot prints and those pay MORE. But undisclosed
weighting sensitivity is large: phi_A 0.478 / 0.493 / 0.584 / 0.699 by
convention; phi_B median 0.3951 vs **mean 0.4386**. PROTOCOL §4 mandates
medians, but portfolio drag is a mean, and it is 0.44.

## KV3 liquidity tilt — FAILS TO KILL
Reweighting fill events by cost_frac decile onto the full lead-14
distribution: phi_B 0.3951 → 0.3878; phi_A 0.4777 → 0.4751.

## KV4 sign flip — REAL, BUT THE MECHANISM IS TICK DISCRETENESS

Not the trivial denominator artifact (`dev` rises 26.1 → 93.3bp while quoted
half rises faster, 54.3 → 279.1bp). Bucketing all 17,194 prints by quoted
width in TICKS:

| width | interior grid pts | vol | phi (VW) | frac@mid | frac inside |
|---|---|---|---|---|---|
| 1 tick | **0** | 25,328 | **0.889** | 0.000 | 0.188 |
| 2 | 1 | 39,859 | 0.694 | 0.152 | 0.413 |
| 3–4 | 2 | 13,128 | 0.565 | 0.089 | 0.598 |
| 5–8 | 5 | 16,341 | 0.624 | 0.154 | 0.508 |
| >8 | 13 | 5,371 | **0.389** | 0.175 | 0.789 |

In a one-tick market there is **no attainable price strictly inside the
touch**, so phi is forced to ~1 by arithmetic. phi tracks the count of
attainable interior prices, not negotiation. Both of the runner's
"independent checks" share the mechanism: `frac_vol_inside` IS the
discreteness variable, and the instrumented denominator uses the same tick
width. Spec wiggle on `target=stale` is null (+0.028 p=0.520 / −0.040
p=0.376 / +0.031 p=0.475). Clipping is immaterial (0.01% hits the 3.0 clip).

## KV5 restatement — REPRODUCES; one hybrid cell

65.22 / 48.98 / +11.32bp median / +20.56bp mean / 67.5% positive — exact.
130.4 → 107.8bp, +6.39% → **+6.616%**, +0.226pp = 3.5% of edge. CONFIRMED.
The "mean-paired 89.2bp" cell mixes a mean delta with a median base; all-mean
is 140.4bp (mean assumed round trip 181.5bp). Scaling against the median toll
flatters a right-skewed distribution.

**EXIT-SYMMETRY LEVERAGE: the restatement turns negative at phi_exit =
0.605** (0.561 on means). phi rises to 0.468 in the last five minutes, rises
with size, and the exit is a crowded pre-print sell at elevated IV. Not
remote. ANOM-6 is half the claim, not a footnote.

## THE DECIDING CHECK — the note's own flip-condition #2, which it did not run

P2.md states: *"recompute restricting to prints ≥ 10 contracts. If phi_B on
large prints is ≥ 0.50, the 0.40 recommendation dies."* Named, said to need
no purchase, **not run**. From the raw tape (both-legs-printed events):

| min print size | n events | phi_B | 95% CI (season) | phi_A |
|---|---|---|---|---|
| any | 424 | 0.4028 | [0.3832, 0.4198] | 0.478 |
| ≥ 5 | 190 | 0.4317 | [0.3941, 0.4849] | 0.534 |
| ≥ 10 | 120 | **0.4733** | **[0.4038, 0.5398]** | 0.554 |
| ≥ 25 | 39 | **0.5088** | **[0.4418, 0.6429]** | 0.703 |

**THE STATED KILL CRITERION IS MET.** At a $15.25 median straddle, 25
contracts ≈ $38k premium — under P4 (1–3%/name) that is the operative clip
for any book above ~$1.3M. 0.40 is the price of a 1-lot; the strategy does
not trade 1-lots.

## KV6 coverage and "stable constant" — REFUTED

539/570 = 94.6% from 2023Q2, **0/397 before**. Pre-2023 differs materially
(cost_frac 1.62% vs 1.33%, spread $0.45 vs $0.40, stale_legs 6.0% vs 4.2%,
gross tail 10.6% vs 6.8%) and holds 41% of events.

The **in-sample** regime is not stable either. Median lead-14 cost_frac runs
1.00–1.45% through 2025Q3, then **2.28 / 2.38 / 2.83 / 2.94%** in
2025Q4–2026Q3. Confirmed independently on the tape (tape half-frac 0.99% →
2.46%, Spearman +0.348 p=9e-17) with no panel drift (panel/tape ratio
Spearman −0.010, p=0.817) — real widening. phi_B follows:
**Spearman(season, phi_B) = −0.106, p = 0.014**; last four seasons 0.353 vs
0.410; **2026Q3 = 0.235**. The "stable microstructure constant" claim was
made on phi_A, the definition that hides it.

## ANOM-8 — a semantics defect the guards did not catch

`phi_implied_entry`'s prose says "on the entry day"; `volume_entry` is
described as "entry-day volume" throughout. It is **15:00–16:00 ET only**. So
"median entry-day volume 33 contracts", "20.2% had a leg that never traded"
and "5.4% zero prints both legs" are LAST-HOUR statements, and the proposed
"abort if clip exceeds ~25% of recent daily volume" rests on a denominator
off by an unknown multiple. The assertion lambda only range-checks [0,3], so
G1 passes — the exact failure class G1 exists to prevent (`dte_entry`
precedent). phi itself is unaffected; the capacity conclusion is not.

## Strongest alternative explanation

Price-grid discreteness plus trade-moment selection, with no fill-quality
content. phi is mechanically pinned near 1 where the tick grid offers no
interior price, and free to fall only where it does. Separately, the prints
we see are moments a maker chose to tighten (quiet 0.867 vs active 0.954), so
the extra discount converting phi_A into phi_B is bought by conditioning on a
state we cannot summon on demand. Under this reading phi_B = 0.40 is not "the
fraction of the spread we will pay" but "the fraction paid by whoever
happened to trade, at 1.25 lots, in a market whose tick grid allowed it." The
size ladder and the tick-width table both point UP from 0.40 for a real
order. The regime alternative is also live and confirmed above.

## DELIVERABLE: is phi = 0.40 safe for POLICY? **NO.**

It answers a narrower question than POLICY asks: the marginal 1-lot, in the
2023Q2–2025Q3 tight regime, entry leg only, conditional on a print occurring.

Honest uncertainty band, ENTRY leg:

| basis | value |
|---|---|
| statistical CI at the measured 1-lot margin | 0.375 – 0.416 |
| + weighting/aggregation choice | 0.34 – 0.44 |
| + spread regime (2023-25 vs 2026) | 0.24 – 0.46 |
| + clip size 1 → 25 contracts | up to 0.51 – 0.64 |
| **defensible planning band** | **0.40 – 0.55, point ~0.47** |
| **round trip, exit unmeasured** | **phi_e + phi_x ∈ [0.8, 1.2]** vs incumbent 1.0 |

**Safe to promote (not nothing):**
1. **"Mid-or-better fills only" is REFUTED** — 7.7% of volume at mid
   [5.9, 9.3]; 9.5% of events see half their volume there. Withdraw it.
2. The incumbent **phi = 0.5/side is now evidence-backed rather than
   inherited** — it sits inside the size- and regime-aware band. Regrade the
   BASIS, keep the NUMBER.
3. **phi = 0.40 is a measured FLOOR** (1-lot marginal price), not expected fill.
4. **phi decreases in quoted width (ticks) and increases in clip size** —
   that is the right functional form and it is measurable today.
5. The capacity concern is real, but its denominator must be re-derived from
   FULL-DAY volume before any "25% of daily volume" rule is written.

**Highest-value next step (free):** re-run `fills` with size- and
width-conditioned phi. **Highest-value purchase:** exit-day tcbbo for the
same 539 events — the restatement's sign turns on it.
