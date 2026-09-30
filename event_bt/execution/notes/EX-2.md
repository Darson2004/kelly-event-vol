# EX-2 — Entry-lead cost curve

- **Cell:** EX-2 (persona: cost-analyst), priority 100
- **Tick:** 1 · **alpha_1 = 0.060793**
- **Panel:** `panel_liquid.csv`, sha256 `c88784ed03f030c2…` (frozen; unmodified)
- **Probes logged:** E0001–E0024 (24 entries, all `hyp=EX-2`, all on the frozen hash)
- **Semantics:** `dict` 7/7 PASS before any grading (G1 satisfied)
- **G2 compliance:** every `policy` run used `--metric cost`. No `net`, no `gross`
  was computed anywhere in this cell. Verified against the log:
  `any(metric in {net,gross}) == False`.
- **Verdict: SUPPORTED** (measurement, not a bet — see the sign note below)

---

## 1. Mechanism

The strategy enters at T−14 for one reason: the source paper did. Nobody has
priced that choice on our own tape.

Two forces run in opposite directions as you walk toward the print:

- **Volume/attention.** Approaching earnings, option volume and market-maker
  competition in the front expiry rise. More two-sided flow → tighter quotes →
  *lower* cost.
- **Event risk.** The same approach loads the quote with an un-hedgeable jump.
  A maker widens to be paid for it → *higher* cost.

There is a third force specific to holding the *same* expiry fixed: entering
later means buying a shorter-dated option, so the straddle mid (the denominator
of `cost_frac = spread / (2·mid)`) shrinks. All else equal, that mechanically
*raises* the fractional toll of a later entry. So the denominator works
**against** the "later is cheaper" hypothesis, which makes any measured
later-is-cheaper result conservative.

Which of the first two dominates is an empirical question with no theoretical
answer, and the sign was **not pre-committed** (QUEUE.yaml: "no pre-commitment —
this is a measurement, not a bet"). The full 10-pair grid was specified before
any output was read, run in two batches, and read once. Nothing was re-run
after seeing a result; no cell was selected post hoc.

Within-event pairing makes this near-confound-free: same event, same ticker,
same expiry, same season, same regime — only the entry day differs.

---

## 2. Probes run

### 2a. Primary — paired within-event policy grid, `--metric cost`

All 10 unordered pairs of leads {3,5,7,10,14} were run. Every pair had **967
paired events** and **25 effective clusters** (seasons) — far above the pack's
"below 4 clusters the CI is untrustworthy" line, so both the permutation p and
the cluster CI are admissible here.

`median_diff_a_minus_b` is in units of `cost_frac` (one-way half-spread as a
fraction of straddle mid). Negative = lead **a** is CHEAPER than lead **b**.

| entry | a | b | median diff (a−b) | perm p | cluster CI95 | frac a>b | a median | b median | clears α₁? |
|---|---|---|---|---|---|---|---|---|---|
| E0001 | 3 | 5 | **0.00000** | 1.00000 | [0.00000, 0.00000] | 0.3423 | 0.01216 | 0.01242 | no |
| E0002 | 3 | 7 | −0.00017 | 0.07796 | [−0.00067, +0.00004] | 0.4716 | 0.01216 | 0.01278 | **no** (0.078 > 0.0608) |
| E0003 | 3 | 10 | −0.00076 | **0.00050** | [−0.00115, −0.00033] | 0.4343 | 0.01216 | 0.01351 | **YES** |
| E0004 | 3 | 14 | **−0.00177** | **0.00050** | [−0.00225, −0.00128] | 0.3557 | 0.01216 | 0.01463 | **YES** |
| E0005 | 5 | 7 | 0.00000 | 1.00000 | [−0.00004, 0.00000] | 0.4602 | 0.01242 | 0.01278 | no |
| E0006 | 5 | 10 | −0.00080 | **0.00050** | [−0.00121, −0.00041] | 0.4385 | 0.01242 | 0.01351 | **YES** |
| E0007 | 5 | 14 | −0.00150 | **0.00050** | [−0.00192, −0.00090] | 0.3744 | 0.01242 | 0.01463 | **YES** |
| E0008 | 7 | 10 | 0.00000 | 1.00000 | [−0.00034, +0.00021] | 0.4902 | 0.01278 | 0.01351 | no |
| E0009 | 7 | 14 | −0.00124 | **0.00050** | [−0.00156, −0.00096] | 0.3981 | 0.01278 | 0.01463 | **YES** |
| E0010 | 10 | 14 | −0.00061 | **0.00050** | [−0.00099, −0.00021] | 0.4488 | 0.01351 | 0.01463 | **YES** |

`perm_p = 0.00050` is the **resolution floor** of the 2000-permutation test
(1/2001). The true p is ≤ 0.0005; the harness cannot resolve further. That is
not a rounding artefact I chose — it is the frozen `N_PERM`.

**Sign result (recorded now that the grid is read, once):** every single one of
the 10 differences is ≤ 0. The cost curve is **monotone increasing in entry
lead**. Later entry is cheaper. The volume/tightening force beats the
event-risk-widening force at every distance tested, and it beats it *despite*
the shrinking-denominator effect pushing the other way.

**Dose–response.** The four comparisons against the incumbent T−14 are ordered
by distance, monotonically, with no inversions:

    T−10 vs T−14 : −0.00061
    T− 7 vs T−14 : −0.00124
    T− 5 vs T−14 : −0.00150
    T− 3 vs T−14 : −0.00177

A fluke does not usually arrive pre-sorted by dose.

### 2b. Cost curve level per lead (harness `test --target cost_ic`, which reports
`cost_median` with a season-cluster CI). n = 967 at each lead — every one of the
967 events has a row at all five leads, so these are the same events throughout
and the level comparison is not a composition artefact.

| entry | lead | median `cost_frac` | as % of premium | season-cluster CI95 | eff. clusters |
|---|---|---|---|---|---|
| E0012 | T−3  | 0.01216 | **1.216%** | [0.01107, 0.01372] | 25 |
| E0013 | T−5  | 0.01242 | **1.242%** | [0.01115, 0.01418] | 25 |
| E0014 | T−7  | 0.01278 | **1.278%** | [0.01143, 0.01439] | 25 |
| E0015 | T−10 | 0.01351 | **1.351%** | [0.01205, 0.01515] | 25 |
| E0016 | T−14 | 0.01463 | **1.463%** | [0.01312, 0.01593] | 25 |
| E0011 | all  | 0.01312 | 1.312% | [0.01182, 0.01471] | 25 |

**Shape: monotone increasing and convex.** Marginal cost per calendar day of
extra lead, computed from the medians above:

    T−3 → T−5  (2d): +0.026pp  →  0.013pp/day
    T−5 → T−7  (2d): +0.036pp  →  0.018pp/day
    T−7 → T−10 (3d): +0.073pp  →  0.024pp/day
    T−10 → T−14 (4d): +0.112pp →  0.028pp/day

Each extra day of lead costs more than the one before it. The expensive part of
the T−14 choice is the *far* end, not the near end: the T−10→T−14 stretch alone
is 45% of the whole T−3→T−14 gap.

Note the per-lead marginal CIs overlap almost completely. That is exactly why
the paired test is the primary evidence: cross-name dispersion in spread level
swamps the lead effect, and pairing removes it.

The `stat` column of E0012–E0016 is the Spearman of *actual* `lead` against
`cost_frac` **within** a lead bucket (the bucket has 0–4 days of slack). Those
came back −0.080 / +0.089 / +0.057 / −0.063 / +0.035 — sign-inconsistent noise.
The 0–4 day slack inside a bucket carries no usable signal; only the between-
bucket distance does. Reported because it was run, not because it means
anything.

### 2c. Mechanism decomposition — is it the spread or the denominator?

| entry | feature | target | stat (Spearman) | n | sign predicted | match |
|---|---|---|---|---|---|---|
| E0011 | lead | cost_ic (`cost_frac`) | **+0.09855** | 4835 | + | yes |
| E0023 | lead | spread (`entry_spread`, absolute $) | **+0.11345** | 4835 | + | yes |
| E0024 | dte_true | spread (absolute $) | **+0.09998** | 4835 | + | yes |

The absolute-dollar spread rises with lead *more strongly* than the fractional
cost does (+0.113 vs +0.099). Confirmed by the within-event ratio audit below:
walking from T−3 to T−14 on the same event, the **absolute quoted spread widens
×1.389 while the straddle mid only rises ×1.172**. The extra time value you buy
at T−14 (+17%) does not come close to paying for the extra quote width (+39%).

So the finding is not an artefact of the `cost_frac` denominator. It is a real
widening of the dollar quote as you move away from the print.

### 2d. Staleness by lead (G4)

| entry | lead | `stale_rate` | n |
|---|---|---|---|
| E0017 | T−3  | 0.0000 | 967 |
| E0018 | T−5  | 0.0000 | 967 |
| E0019 | T−7  | 0.0000 | 967 |
| E0020 | T−10 | 0.0000 | 967 |
| E0021 | T−14 | 0.0000 | 967 |
| E0022 | all  | 0.0000 | 4835 |

The `stat` is `null` in all six because `stale_dd` has zero variance, so the
correlation is undefined. G4 is satisfied — **no lead is systematically staler
than another, because none of them is stale at all** — but it is satisfied
*vacuously*, and that deserves the flag below.

---

## 3. AUDIT-DIAGNOSTIC (read-only pandas — descriptive, NOT promotable)

These are not inferential and none of the section-2 conclusions rest on them.
They exist to explain the harness output.

**(i) `stale_dd` is degenerate.** `value_counts(dropna=False)` = {0.0: 4778,
NaN: 57}. Not one row in the panel is flagged stale. The detector requires all
four legs (call bid, call ask, put bid, put ask) at the *same strike* to match
the prior session to the cent. For 42 liquid names on near-close marks a 0/4778
rate is plausible, but a detector that never fires cannot distinguish "no stale
marks" from "detector too strict." **The semantic assertion
`set(unique) ⊆ {0,1}` passes trivially on an all-zeros column** — that is a hole
in G1's coverage. This is EX-3's problem, not mine, but EX-3 should be warned
that its headline feature may be constant on this panel.

**(ii) The three p = 1.00000 cells are a tie-mass artefact, not a measured
zero.** The build takes `entry_date = last observation ≤ (ann − lead)` with up
to 4 days of slack, so adjacent lead buckets frequently resolve to the *same
trading day* — i.e. the "paired counterfactual" is literally the same row:

| pair | share of events with IDENTICAL entry_date | share of paired diffs exactly 0 |
|---|---|---|
| 3 vs 5   | **0.3226** | 0.3237 |
| 5 vs 7   | 0.0620 | 0.0641 |
| 7 vs 10  | 0.0072 | 0.0103 |
| 3 vs 7   | 0.0072 | 0.0083 |
| 10 vs 14 | 0.0062 | 0.0093 |
| 3 vs 10, 3 vs 14, 5 vs 10, 5 vs 14, 7 vs 14 | 0.0000 | ≤0.004 |

Actual-lead composition inside each bucket (crosstab `lead_target` × `lead`):
bucket 3 = {3:372, 4:283, 5:280, 6:25, 7:7}; bucket 5 = {5:617, 6:290, 7:57,
8:3}; bucket 7 = {7:954, 8:6, 10:7}; bucket 10 = {10:362, 11:280, 12:285,
13:34, 14:6}; bucket 14 = {14:936, 15:23, 16:1, 17:7}.

So **"T−3 vs T−5" is roughly a third self-comparison** and cannot be resolved by
this panel at all. The long-distance pairs are clean (0.0% identical dates) and
those are precisely the six that cleared alpha. Excluding ties, the adjacent
non-zero medians are 3−5: **+0.00005**, 5−7: −0.00003, 7−10: −0.00007 — i.e.
adjacent steps are coin flips even after the ties are removed.

The one whisper of non-monotonicity in the whole cell: the tie-excluded 3−5
median is **positive** (T−3 fractionally *more* expensive than T−5), which is
what an event-risk-widening effect would look like if it finally bites in the
last few days. It is 0.5 bp of premium. It is not distinguishable from zero and
I am not building anything on it, but it is the only place a U-shape could hide
and the next tick should look there rather than assume the curve is monotone
all the way to T−0.

**(iii) Level table by lead** (medians): spread $0.30 / $0.30 / $0.35 / $0.35 /
$0.40 and mid $12.45 / $12.80 / $13.43 / $14.28 / $14.93 at T−3/5/7/10/14;
`n_strikes` 51 / 50 / 49 / 43 / 41 (the chain thickens toward the print — a
plausible microstructural driver, and EX-4's territory, not spent here).
Within-event median ratios vs T−3: spread ×1.0000 (T−5), ×1.0909 (T−7), ×1.2500
(T−10), ×1.3889 (T−14); mid ×1.0080, ×1.0692, ×1.1237, ×1.1721.

**(iv) Season coverage:** 25 seasons, 2020Q3–2026Q3, 26–42 events each except
2020Q3 (n=2) and 2026Q3 (n=26). 25 effective clusters throughout — the cluster
CI is admissible everywhere in this cell.

---

## 4. Multiplicity

The family is **10 pairwise comparisons**, all pre-specified, all run, all
reported. None discarded.

- **Unadjusted at α₁ = 0.060793:** 6 pairs clear — (3,10), (3,14), (5,10),
  (5,14), (7,14), (10,14), all at p = 0.00050.
- **Bonferroni within the family:** threshold = 0.060793/10 = **0.0060793**.
  All six clear it by more than an order of magnitude (0.0005 < 0.00608).
- **Holm step-down** (sorted p: 0.0005 ×6, 0.07796, 1.0, 1.0, 1.0): the six
  smallest pass against 0.060793/10 … /5 = 0.00608 … 0.01216. The seventh
  (E0002, p = 0.07796) is tested against 0.060793/4 = 0.01520 and fails. Holm
  therefore admits **exactly the same six pairs**.

**The headline survives the multiplicity of its own grid with room to spare.**
E0002 (T−3 vs T−7, p = 0.078) does not clear even the *unadjusted* α₁ and is
reported as a non-result, not as a marginal one.

---

## 5. Committed position

The T−14 entry is the **most expensive of every lead we can test**, and it is
not close: it loses to all four alternatives, the losses are monotone in
distance, six of the ten pairwise tests clear a Bonferroni-adjusted α₁, and the
mechanism decomposes cleanly — the dollar quote widens ×1.39 from T−3 to T−14
while the premium you are buying only grows ×1.17. That is a genuine
microstructure fact about our tape, not an accounting effect of the `cost_frac`
denominator, which if anything runs the other way. The curve is monotone and
**convex**: the marginal toll rises from 0.013pp/day near the print to
0.028pp/day out at T−14, so the incumbent sits on the steepest, most expensive
part of the curve, and 45% of the total T−3→T−14 penalty is incurred in the
final T−10→T−14 stretch alone.

And yet the decision this changes is **not** "move the entry day." It is
"we now know the price of the entry day." The full T−3-vs-T−14 saving is a
median 0.177pp of premium per trade (harness convention: at PHI = 0.5 the
round-trip toll equals `cost_frac`, so 0.00177 of `cost_frac` is 17.7bp of the
trade's own return). Against the graduated +6.39%/trade that is **2.8% of the
edge**; under P4's 1–3% premium sizing it is 0.18–0.53bp of NAV per trade.
Statistically overwhelming, economically modest. The honest framing for the
orchestrator is a **hurdle**, stated before EX-5 is read so it cannot be
rationalised backwards: moving the entry from T−14 to T−3 buys you 17.7bp of
premium and costs you eleven days of pre-print vol repricing, which is where
the strategy's entire thesis lives. **If EX-5 shows the paired gross gives up
more than 17.7bp moving T−14 → T−3, T−14 survives on net despite being the
worst lead on cost.** T−10 is the cheap partial: it captures 34% of the
available saving (6.1 of 17.7bp) for only four fewer days of holding, and it is
the lead I would look at first if EX-5 comes back showing gross decays gently.

One thing I cannot do with this panel, and will not pretend to: **separate
"closer to the print" from "closer to expiry."** The expiry is held fixed per
event by construction, so within an event `dte_true = lead + constant` —
perfectly collinear. The within-event paired test, which is my strongest
evidence, has exactly zero power to tell those two stories apart (and E0023 vs
E0024 are near-duplicates for the same reason). Both mechanisms predict the
same sign here, so the *policy* conclusion is unaffected, but nobody should
quote this note as evidence that "spreads tighten into earnings" in general.

### Calibration block

- **Position:** On our 42-name liquid tape, quoted entry cost is **monotone
  increasing and convex in entry lead**; T−14 is the most expensive lead
  available at a median 1.463% of premium versus 1.216% at T−3, a paired median
  penalty of **17.7bp of premium per trade (95% cluster CI [12.8, 22.5]bp)**,
  driven by a ×1.39 widening of the absolute dollar spread against only a ×1.17
  larger premium. This sets a **17.7bp hurdle** that the gross side (EX-5) must
  clear before the entry day should actually move.
- **Confidence: high (>80%).** 6 of 10 pairwise tests at p ≤ 0.0005 surviving
  Holm/Bonferroni at α₁; 967 paired events; 25 effective clusters; all 10 signs
  ≤ 0; perfect dose–response ordering; and an independent mechanism
  decomposition (E0023/E0024 plus the within-event spread/mid ratios) that
  agrees. The 4 nulls are all adjacent pairs explained by a measured tie-mass,
  not by disagreement.
- **Boundary conditions.**
  - Holds for: the 42-name liquid universe, 2020Q3–2026Q3, near-close
    (15:44–15:47 ET) quotes, ATM straddle on the first expiry after the print,
    leads 3–14.
  - Does **not** establish: anything at T−0/T−1/T−2 (untested — and the only
    hint of curvature, the tie-excluded 3−5 median of +0.00005, points at a
    possible minimum near T−5 rather than at T−3); anything about leads > 14;
    anything about small/mid-caps (P5 already excludes them); anything about
    intraday timing (BLOCK-1).
  - Measures **quoted** half-spread, not fills. If the realizable fraction of
    the quoted spread varies with lead — plausibly you can lean on the mid more
    easily in a thick near-print book, which would make the true curve
    *steeper* — the magnitude is wrong. Direction would survive. P2
    ("mid-or-better fills") remains untestable on this data.
  - The T−3-vs-T−5 cell is structurally unresolvable here (32.3% of those
    "pairs" are the same trading day). Treat the near end of the curve as
    coarse: this panel resolves ~3-day steps, not 2-day steps.
- **What would flip this:**
  1. A season-jackknife (auditor's step) showing the T−3-vs-T−14 sign is
     carried by fewer than ~18 of the 25 seasons, i.e. the effect is a
     regime artefact of the 2021–22 vol complex rather than a standing
     microstructure fact.
  2. Rebuilding the panel with a strict `entry_date` match (no 4-day slack) and
     finding the T−10-vs-T−14 gap collapses inside its CI — that would mean the
     gap is driven by bucket-composition rather than lead.
  3. A fill-quality dataset showing realized entry slippage at T−14 is a
     *smaller* fraction of the quoted spread than at T−3 by more than 19%
     (1.389/1.172), which would exactly undo the quoted-cost advantage.
  4. Any evidence that `cost_frac` is not the toll actually paid — e.g. if the
     ATM strike selected at T−3 is systematically less liquid than at T−14
     (`n_strikes` moves the other way, 51 vs 41, so this looks unlikely).
- **Evidence weight:** 10 of 10 pairwise signs ≤ 0; **6 of 10 clear α₁ = 0.0608
  both unadjusted and after 10-fold Bonferroni/Holm**, at paired median effects
  of 6.1 to 17.7bp of premium; 4 of 10 null, all adjacent pairs, all with a
  measured tie-mass explanation; 5 of 5 per-lead level probes monotone in the
  same direction; 2 of 2 mechanism probes (E0023, E0024) sign-consistent;
  0 of 4835 rows flagged stale.

**Detectable-effect-size statement for the four nulls.** At n = 967 paired
events the sign-permutation test resolved a 6.1bp median difference (E0010) at
p ≤ 0.0005, so the floor is well below that. Reading the cluster CIs directly:
E0008 (7 vs 10) bounds any median difference to **within ±3.4bp of premium**;
E0005 (5 vs 7) to **within 0.4bp**; E0002 (3 vs 7) to **within 6.7bp** at
p = 0.078. E0001 (3 vs 5) is **not a power statement at all** — with 32.3% of
pairs being the same trading day, that cell is structurally unresolvable and
should be reported as BLOCKED-BY-CONSTRUCTION, not as a null.

---

## 6. Verdict

**SUPPORTED.**

EX-2 asked a measurement question and got a decisive answer: cost is monotone
increasing and convex in entry lead over T−3…T−14, T−14 is the worst available
lead on the cost axis, and the effect is 17.7bp of premium at the extremes with
p ≤ 0.0005 after multiplicity correction at α₁ = 0.060793.

Sub-verdicts within the cell, so nothing is over-claimed:

- **SUPPORTED** — (3,14), (5,14), (7,14), (10,14), (3,10), (5,10): later entry
  is cheaper, all at p ≤ 0.0005, all clearing Holm at α₁.
- **NULL-WITH-POWER** — (7,10), (5,7): any median cost difference is smaller
  than 3.4bp and 0.4bp of premium respectively.
- **NULL, does not clear α₁** — (3,7): −1.7bp at p = 0.07796, CI
  [−6.7, +0.4]bp. Directionally consistent, not admissible.
- **BLOCKED-BY-CONSTRUCTION** — (3,5): 32.3% of the "pairs" share an entry
  date; this panel cannot resolve a 2-day step at the near end.

### Implication for POLICY rule P1 — for the orchestrator's T5 step, NOT edited here

P1 ("Enter at T−14", currently graded **ASSUMED**) can no longer be described as
untested. It has now been tested on one of its two axes and **lost on that
axis**: T−14 is the most expensive of the five leads, by 24.7bp of premium
unpaired / 17.7bp paired versus T−3.

That is *not* sufficient to change the rule. The recommended grade change is
from **ASSUMED** to something like **MEASURED-ON-COST / PENDING-NET**, with the
basis line recording the 17.7bp hurdle. The rule should only move after EX-5
reports the paired gross and net grids. If EX-5 shows the gross penalty of
entering late is under 17.7bp, P1 should move to T−3 (or, more cautiously,
T−10, which banks 6.1 of the 17.7bp for only four fewer holding days). If the
gross penalty exceeds 17.7bp, P1 stands at T−14 and this note becomes the
documented reason why the expensive lead is nonetheless the right one.

### Trial accounting for this cell

24 logged probes (E0001–E0024): 10 inferential paired policy comparisons (the
alpha-bearing family), 14 descriptive/mechanism `test` runs which produce no
p-value and bear no alpha. Cumulative pack trials after EX-2: 24.
