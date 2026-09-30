# EX-2 AUDIT — entry-lead cost curve

- **Auditor:** finding-auditor (fresh context), tick 1
- **Audited note:** `notes/EX-2.md` (cell EX-2, cost-analyst)
- **Panel:** `panel_liquid.csv`, sha256 `c88784ed03f030c2…` — verified byte-identical
  to `SHA256SUMS`. Nothing in the pack was modified.
- **Log at audit start:** 24 entries (E0001–E0024). At audit end: 53
  (24 verbatim replays E0025–E0048, 5 new spec-wiggle probes E0049–E0053).
- **G2:** no `--metric net` and no `--metric gross` appears anywhere in the log,
  before or after this audit. All 20 `policy` runs used `--metric cost`. I did
  not compute net or gross.

## VERDICT: **FRAGILE**

The headline number is real and survives everything I threw at it. Two named
sub-claims in the note do not: the **convexity** claim and the
**(10,14) / "T−10 banks 6.1bp"** claim. The **mechanism** claim is refuted
outright (right sign, wrong story), and that changes what the 17.7bp figure
means for POLICY.

---

## 1. Replay — numbers match: YES, all of them

All 24 logged commands re-run verbatim against the frozen hash. Every figure in
§2a, §2b, §2c, §2d and §3(iii) of the note reproduces to the printed digit:

- 10 paired `policy` medians: 0.00000 / −0.00017 / −0.00076 / −0.00177 /
  0.00000 / −0.00080 / −0.00150 / 0.00000 / −0.00124 / −0.00061, all with the
  stated `perm_p`, `ci95`, `frac_a_greater`, 967 paired events, 25 clusters.
- Per-lead `cost_median` 0.01216 / 0.01242 / 0.01278 / 0.01351 / 0.01463 and
  the within-bucket Spearmans −0.08036 / +0.08853 / +0.05663 / −0.06323 / +0.03473.
- E0011 +0.09855, E0023 +0.11345, E0024 +0.09998; stale_rate 0.0000 ×6.
- Descriptives: median spread 0.30/0.30/0.35/0.35/0.40, mid 12.45/12.80/13.43/
  14.28/14.93, `n_strikes` 51/50/49/43/41, within-event ratios spread ×1.3889 /
  mid ×1.1721 at T−14. All confirmed.

No number in the note traces to nothing. **Not fabricated.**

## 2. KV1 — season jackknife: FAILS TO KILL (decisively)

Leave-one-season-out on the pooled paired median:

| pair | full | jackknife range | max p |
|---|---|---|---|
| (3,14) | −0.00177 | [−0.00182, −0.00168] | 0.0005 |
| (10,14) | −0.00061 | [−0.00067, −0.00054] | 0.0005 |

Leave-one-**year**-out, all six clearing pairs: every one keeps its sign and
p ≤ 0.0015 with any single year removed (worst cell: (5,10) drop-2026,
−0.00062, p=0.0015).

Per-season sign count: **(3,14) negative in 23/25 seasons** (positive only in
2020Q4 +0.00005 and 2023Q1 +0.00060). Well clear of the runner's own ≥18/25
flip line. **(10,14) negative in 19/25**, but one of those is −4.9e−17, so
strictly 18/25 — sitting exactly on the flip line.

This is not a 2021–22 vol-complex artefact. No season and no year carries it.

## 3. KV2 — tie mass / entry_date slack: FAILS TO KILL, and inverts

Same-entry-date rate for the six clearing pairs: (3,10) 0.0%, (3,14) 0.0%,
(5,10) 0.0%, (5,14) 0.0%, (7,14) 0.0%, **(10,14) 0.62%** (6 events). Tie mass
is confined to the three adjacent nulls, exactly as the note said.

Restricting to realised gap **exactly nominal** strengthens every pair:

| pair | full | gap == nominal | n |
|---|---|---|---|
| (3,10) | −0.00076 | −0.00076 (p .0005) | 881 |
| (3,14) | −0.00177 | **−0.00239** (p .0005) | 343 |
| (5,10) | −0.00080 | −0.00131 (p .019) | 66 |
| (5,14) | −0.00150 | −0.00123 (p .0005) | 624 |
| (7,14) | −0.00124 | −0.00124 (p .0005) | 923 |
| (10,14) | −0.00061 | **−0.00187** (p .0005) | 333 |

The runner's flip-condition #2 ("strict `entry_date` match collapses (10,14)")
is falsified in the opposite direction: the pooled estimates are **attenuated**
by realised-gap compression, not inflated. The 17.7bp policy figure is the
right quantity (the policy operates on buckets) and is conservative.

### 3b. But the CONVEXITY claim does not survive (new)

The note computes marginal cost per day on **nominal** bucket labels
(2/2/3/4 days). The **realised** mean lead per bucket is 3.98 / 5.43 / 7.03 /
**11.01** / 14.05 — bucket 10 is really T−11, because `ann − 10 days` lands on a
weekend for ~65% of events and the entry slips back to the prior Friday. Real
step sizes are 1.45 / 1.60 / 3.98 / 3.04 days, not 2/2/3/4:

| step | Δcost | pp per **nominal** day | pp per **realised** day |
|---|---|---|---|
| T−3→T−5 | +0.026pp | 0.0131 | 0.0180 |
| T−5→T−7 | +0.036pp | 0.0180 | 0.0224 |
| T−7→T−10 | +0.073pp | 0.0244 | **0.0184** |
| T−10→T−14 | +0.112pp | 0.0280 | 0.0369 |

On realised distance the sequence is 0.018 / 0.022 / **0.018** / 0.037 — not
monotone. "Each extra day of lead costs more than the one before it" is an
artefact of the nominal bucket labels. **Strike the convexity claim.** The
related "45% of the penalty is in the T−10→T−14 stretch" is likewise a
statement about a 3.04-day step mislabelled as a 4-day step.

## 4. KV-new — DAY-OF-WEEK stratification: this is what kills (10,14)

The slack the panel allows is not random; it is a weekend calendar. Entry
weekday composition by bucket:

| bucket | Mon | Tue | Wed | Thu | Fri |
|---|---|---|---|---|---|
| 3 | .277 | .051 | .012 | .005 | **.655** |
| 5 | .000 | .000 | .071 | .302 | **.627** |
| 7 | .050 | .301 | .300 | .294 | .056 |
| 10 | .271 | .049 | .006 | .022 | **.653** |
| 14 | .050 | .303 | .313 | .280 | .054 |

Because `ann − 7` and `ann − 14` land on the same weekday as the print, buckets
7 and 14 are midweek; buckets 3, 5 and 10 are Friday-heavy. Entry weekday is
therefore **near-collinear with the lead bucket within an event** — a third
collinearity the note does not mention, alongside `dte_true`.

Two of the six pairs are immune by construction, and both survive at full
strength:

- **(3,10)**: buckets 3 and 10 have *identical* weekday mixes (Fri .655/.653,
  Mon .277/.271); 91.1% of pairs are same-weekday. −0.00076, p=0.0005.
- **(7,14)**: 95.4% of pairs are same-weekday (gap exactly 7). −0.00124,
  p=0.0005.

Stratifying by announcement weekday (which fixes the weekday cell of both legs):

| pair | strata with median < −1bp |
|---|---|
| (3,14) | **5 / 5** — Mon −0.00142, Tue −0.00205, Wed −0.00107, Thu −0.00242, Fri −0.00319 |
| (3,10) | 4 / 5 |
| (5,14) | 4 / 5 |
| (7,14) | 4 / 5 (all three large strata negative, p ≤ .0005) |
| (5,10) | 3 / 5 |
| **(10,14)** | **1 / 5** |

(10,14) by announcement weekday:

    ann=Thu  n=285  Mon->Thu  gap 4   med -0.00233  p 0.0005
    ann=Tue  n=290  Fri->Tue  gap 3   med -0.00005  p 0.845
    ann=Wed  n=288  Fri->Wed  gap 2   med -0.00001  p 0.670
    ann=Mon  n= 55  Fri->Mon  gap 4   med +0.00013  p 1.000
    ann=Fri  n= 49  Tue->Fri  gap 4   med +0.00030  p 0.482

Three of the four strata with the **full 4-day realised gap** show zero or a
positive sign. The one stratum that shows −23bp is the Thursday-announcement
group, where the T−10 bucket lands on a Monday. Realised distance does not order
the strata; the weekday does. Additive weekday adjustment takes (10,14) from
−0.00061 (p=.0005) to **−0.00003 (p=0.771)**; the same adjustment leaves
(7,14) at −0.00124 and (3,10) at −0.00072, both p=0.0005. (The additive
adjustment over-corrects — weekday is partly a mediator here — which is exactly
why the stratified table above is the primary read. The two agree.)

**Conclusion:** (10,14) is a weekday/announcement-day effect, not a lead effect.
(3,14) is not — it is negative in every weekday cell, with cell medians ordered
by realised gap (gap 9 → −0.00102, gap 10 → −0.00211, gap 11 → −0.0017/−0.0024/−0.0032).

## 5. KV3 — dte_true confound: partially separable, and it favours event-proximity

Within an event `dte_true = lead + overhang` with `overhang = expiry − ann_date`
fixed, so the paired test has zero power (confirmed: the identity holds for
1.000 of rows). But overhang *varies across events* (median 2 days; 1/2/3 days
covers 88% of events; it is essentially `Friday − ann_weekday`), which gives a
small amount of leverage the note did not use:

At **fixed lead bucket**, ρ(overhang, cost_frac) = +0.011 / +0.095 / +0.036 /
+0.113 / **−0.009**; within-ticker demeaned +0.019 / +0.083 / +0.018 / +0.082 /
**−0.056**. Sign-inconsistent, and negative at the lead that matters most
(T−14). Extra days-to-expiry at a fixed distance from the print do **not**
reliably raise cost. That is weak evidence *against* a pure expiry-proximity
story and *for* an event-proximity story — better than the note's "inseparable",
though with only 1–3 days of leverage against an 11-day contrast the power is
limited.

Caveat found in the same test: the overhang tercile split is nearly a split by
announcement weekday, so this cut and §4 are the same cut. (10,14) is
−0.00108/−0.00005/+0.00022 across short/mid/long overhang — the same
one-stratum pattern as §4.

New spec-wiggle probe **E0049**: `dte_true → cost_ic` = **+0.13482**, *larger*
than `lead → cost_ic` (+0.09855, E0011). Cross-sectionally, time-to-expiry is
the better predictor of fractional cost. Weak evidence (cross-sectional), but it
is the wrong direction for the note's framing.

## 6. KV4 — denominator: the note's arithmetic is right, its mechanism is wrong

Paired on **raw dollar spread**, all six clearing pairs are negative at
p=0.0005: (3,14) −$0.10 [CI −0.10, −0.06], (7,14) −$0.05, (10,14) −$0.05, etc.
The ×1.3889 spread / ×1.1721 mid ratios reproduce exactly. So the finding is
**not** a `cost_frac` denominator artefact in the narrow sense the note tested.

But the note draws the wrong mechanism from it. An ATM straddle has
mid ≈ 0.8·S·σ·√T and vega ≈ 0.8·S·√T, so `cost_frac ≈ w/(4σ)` where `w` is the
market maker's bid-ask width **in vol terms**. Within-event median ratios,
T−14 vs T−3:

    sqrt(dte)  x1.5584      <- vega grows this fast
    spread     x1.3889      <- dollar quote grows SLOWER than vega
    mid        x1.1721
    IV level   x0.7309      <- implied vol is ~37% HIGHER at T-3
    IV width   x0.8496      <- vol-terms quote is ~18% WIDER at T-3
    cost_frac  x1.1617   =  0.8496 / 0.7309   (checks exactly)

Paired sign tests confirm it: the vega-normalised quote width is **wider near
the print**, not tighter — (3,14) +0.00181 p=0.0005; (3,10) +0.00227 p=0.0005;
(7,14) +0.00081 p=0.0005; (10,14) 0.00000 p=1.0.

So the note's §2c/§5 statement — *"the volume/tightening force beats the
event-risk-widening force at every distance tested"* and *"a real widening of
the dollar quote as you move away from the print"* — is **backwards**. The
event-risk force wins on quote width, exactly as the note's own §1 predicted it
might. The dollar spread is larger at T−14 only because the option has more
vega; per unit of vega the maker is *tighter* at T−14. What makes T−3 cheap in
fractional terms is that implied vol is 37% higher there, inflating the
denominator faster than the maker widens.

**The measured 17.7bp is real. The reason for it is the pre-print IV run-up.**

## 7. KV5 — ticker / event concentration: FAILS TO KILL

42 tickers, max single-ticker share of paired events **2.48%** (AAPL, 24/967).
Dropping the top 3 tickers changes nothing (all six pairs keep sign, p=0.0005;
several get *larger*). Worst leave-one-ticker-out for each pair: (3,14) −0.00171,
(7,14) −0.00116, (10,14) −0.00051 — all still p ≤ 0.0005.

Trimming the largest-|diff| decile: five pairs survive ((3,14) −0.00134 p=.0005;
(7,14) −0.00102 p=.0005; (3,10) −0.00052 p=.0035). **(10,14) dies: −0.00015,
p=0.134.** Same weak link again.

## 8. KV6 — trial count and multiplicity: HONEST

- Exactly **24** EX-2 entries existed pre-audit. All 24 are reported in
  `notes/EX-2.md` (E0001–E0024 each appears in a table). **No hidden variants,
  no abandoned probes, no undisclosed re-runs.** The note's trial accounting
  (10 inferential + 14 descriptive) is accurate.
- All 24 ran on the single frozen hash `c88784ed03f030c2`.
- No `--metric net` / `--metric gross` anywhere. G2 clean.

The permutation p is pinned at the 1/2001 resolution floor, so a minimum-Bayes-
factor calculation at the *reported* p understates the evidence badly
(min BF = −e·p·ln p = 96.8:1 at p=0.0005; 13.9:1 after Bonferroni ×10; 3.8:1
after ×53 for every trial in the pack — the last giving posterior odds 0.42:1 at
a 1:9 prior, i.e. under 50%). That floor-based calculation is the wrong
instrument here. A conservative binomial **sign test** on the same paired
differences is the honest bound:

| pair | neg / pos | sign-test p | min BF | posterior odds @1:9 prior |
|---|---|---|---|---|
| (3,14) | 621/344 | 3.7e−19 | 2.4e16 | overwhelming |
| (5,14) | 604/362 | 6.5e−15 | 1.7e12 | overwhelming |
| (7,14) | 581/385 | 3.1e−10 | 5.5e7 | overwhelming |
| (3,10) | 544/420 | 7.3e−05 | 530:1 | 59:1 |
| (5,10) | 539/424 | 2.4e−04 | 187:1 | 21:1 |
| **(10,14)** | 524/434 | **4.0e−03** | **16.6:1** | **1.8:1** |
| (3,7) | 503/456 | 1.4e−01 | 1.4:1 | 0.15:1 |

(3,14) clears any multiplicity penalty anyone could construct — ×10 for the
grid, ×53 for every trial in the pack, ×1000 for the whole research programme.
**(10,14) does not:** at Bonferroni ×10 its sign-test p is 0.040, min BF ≈ 3.4:1,
posterior odds at a 1:9 prior ≈ 0.38:1. Note also that the harness's
median-based sign-permutation reports 0.0005 for (10,14), ~8× more optimistic
than the sign test; the gap reflects real asymmetry in the difference
distribution, and for a *location* claim the sign test is the safer read.

## 9. Strongest alternative explanation

**The 17.7bp cost saving and the gross cost of entering late are the same
phenomenon, not two independent quantities to be netted.** `cost_frac` is
`spread/(2·entry_mid)` and `gross_ret` is `(exit_mid − entry_mid)/entry_mid`.
Both are divided by `entry_mid`. And `exit_mid` and `exit_date` are computed
once per event in `cmd_build`, *outside* the lead loop — verified: 0 of 967
events have more than one distinct `exit_mid`. Therefore for any pair of leads
a and b on the same event, the paired gross difference is a deterministic
function of the two entry mids alone:

    gross_a - gross_b = exit_mid * (mid_b - mid_a) / (mid_a * mid_b)

EX-2 has already published `mid_b/mid_a = 1.1721` for (3,14). So EX-5's paired
`--metric gross` grid carries **no information EX-2 has not already produced**,
and the paired net difference is likewise fully determined by `entry_mid` and
`entry_spread` at the two leads — quantities in this note. The "hurdle" is not
a hurdle: the comparison is arithmetically closed before EX-5 runs. (I did not
compute gross or net; this is an identity read off `cmd_build`, plus the
already-published mid ratio.)

The mechanism section makes the same point physically. The straddle mid is
*lower* at T−3 than at T−14 (theta beats the IV run-up between those two dates
on this tape, ×0.853). The lower entry mid is simultaneously what makes
`cost_frac` smaller and what would make a mid-to-a-common-exit gross return
larger. Any "cost saving vs gross give-up" trade-off computed from this panel is
one variable wearing two hats.

Secondary alternatives checked and largely ruled out:

- *Regime / "it was 2022"*: ruled out (§2).
- *Name concentration*: ruled out (§7).
- *Bucket-collapse from entry_date slack*: ruled out, runs the other way (§3).
- *Liquidity proxy (chain thickness)*: `n_strikes` moves 51→41 with lead, and
  new probe **E0050** gives ρ(n_strikes, cost_frac) = −0.078 — consistent with a
  thick-chain-is-cheap story, but **E0051** gives ρ(n_strikes, entry_spread) =
  **+0.465** (wrong sign for a liquidity story; `n_strikes` mostly tracks the
  underlying's price level). **E0053** ρ(entry_mid, entry_spread) = **+0.774** —
  the dollar spread is dominated by the premium level, i.e. by vega, which is
  the §6 finding. EX-4's territory; not resolvable here.
- *Day-of-week*: **NOT ruled out for (10,14) and (5,10)** — it is the leading
  explanation for both (§4). Ruled out for (3,14), (3,10) and (7,14).

## 10. ANOM-1 — the staleness detector, diagnosed

`cmd_build` sets `stale = int(p.call_bid == st["cb"] and p.call_ask == st["ca"]
and p.put_bid == st["pb"] and p.put_ask == st["pa"])` — a **4-way exact
float equality** against the prior session at the same strike and expiry.

Measured on the source chains (`data/canonical_liquid/chains.csv`, read-only,
6 tickers: AAPL, MSFT, XOM, COIN, SMCI, CAVA; 518,008 contract-days), restricted
to |strike/spot − 1| ≤ 2% — the region the panel's ATM picker actually uses:

    per-leg unchanged rate, consecutive sessions:  ~1.06-1.09% per leg
    >= 1 of 4 legs unchanged:                       3.37%
    >= 2 of 4 legs unchanged:                       0.82%
    straddle mid exactly unchanged:                 0.59%
    all 4 legs unchanged (what the detector needs): 0.019%
    zero-bid leg at ATM:                            0.00%

**Diagnosis: the detector is not broken, it is too strict by roughly two orders
of magnitude.** At a 0.019% firing rate the expected count over 4,778 non-null
panel rows is **~0.9 events**; observing 0 is exactly what the design predicts.
A 0/4778 read therefore carries no information — it is equally consistent with
"no stale marks" and with "a detector that fires once per five thousand rows."
The 57 NaNs come from a second-order issue: `prev = obs_all[obs_all < entry_date]`
takes the ticker's prior observation date across *all* expiries, then requires a
row at (prev_date, chosen expiry, entry-day ATM strike); when that exact strike
was not quoted on the prior session, `stale` is left NaN.

A correct detector, for the orchestrator to weigh **between ticks** (deliberately
not implemented here):

1. **Graded, not binary** — `n_unchanged_legs ∈ {0..4}`, or the run-length of
   consecutive unchanged sessions per leg. On this universe that yields a live
   column with ~3.4% / 0.8% / 0.02% mass instead of a constant.
2. **Economic, not byte-identity** — flag a quote whose mid (or implied vol) is
   unchanged *while the underlying moved* beyond a threshold. A mark that
   ignores a real spot move is a mark, not a price; a mark that moves by a penny
   is not thereby a price. The current test catches neither.
3. **Book-quality flags the current one omits** — zero/absent bid, crossed or
   locked quote, spread beyond a multiple of the contract's own trailing median.
   (Zero-bid is 0.00% at ATM here, so this universe is genuinely clean — but
   that has now been *shown*, not assumed.)
4. **Fix the G1 coverage hole** — `set(unique) ⊆ {0,1}` is satisfied by an
   all-zeros column. The assertion class must also reject **degenerate** columns
   (`nunique() > 1`, or an expected-rate band). Otherwise a dead detector passes
   semantics, which is precisely what happened. The runner is right that this is
   a real hole; it belongs in AMEND-1.

The note's own flag on this is accurate and appropriately scoped. EX-3 should be
treated as **UNTESTABLE as the panel is currently built**, and G4 as satisfied
vacuously for every EX-2 result.

---

## 11. What stands, what falls

**STANDS (REPLICATED-strength):**

- T−14 is the most expensive lead tested on `cost_frac`: 1.463% vs 1.216% at T−3.
- Paired T−3 vs T−14 penalty **−0.00177 (17.7bp of premium), CI [12.8, 22.5]bp**.
  Survives season jackknife (23/25), year jackknife, ticker jackknife, top-decile
  trimming, strict same-day exclusion (strengthens to −23.9bp), every one of five
  weekday strata, and a sign test at p = 3.7e−19.
- (5,14) and (7,14) at the same strength.
- (3,10) and (5,10) at strong-but-lesser strength (sign-test p 7e−5 / 2e−4).
- Monotone ordering of the five per-lead medians.
- The effect is present in raw dollar spread, not only in the ratio.

**FALLS:**

- **Convexity.** Artefact of nominal-vs-realised bucket spacing (§3b).
- **(10,14) = −6.1bp, and with it "T−10 banks 34% of the saving for four fewer
  holding days."** One of five announcement-weekday strata carries it; it dies
  under weekday adjustment (p=0.771), under top-decile trimming (p=0.134), and
  under honest ×10 multiplicity on a sign test (posterior odds 0.38:1). This is
  the single most consequential correction, because T−10 is the note's
  recommended cautious move.
- **The mechanism story.** Quote width in vol terms is *wider* near the print,
  not tighter. The cost gradient is driven by the IV-level denominator (§6).

**STRUCTURALLY UNSOUND (not the runner's error — a panel/harness property):**

- The "17.7bp hurdle EX-5's gross must clear" framing. `exit_mid` is common
  across all five lead rows of an event, so the paired gross grid is a
  deterministic function of the entry mids EX-2 has already published (§9).

## 12. Recommendation on POLICY.md

**Do not write 17.7bp into POLICY.md as "the number EX-5's gross must clear."**
Write it as a *measurement* — "median paired quoted-cost penalty of the T−14
entry versus T−3, 17.7bp of premium [12.8, 22.5], 967 events, 25 seasons" — and
attach three caveats: (i) it is a *quoted* half-spread, not a fill; (ii) the
gradient is driven by the pre-print IV run-up inflating the denominator, so it
is not independent of the gross side; (iii) `exit_mid` is shared across leads, so
the paired gross/net comparison is already determined by numbers in EX-2 and is
not an independent confirmation. Drop the T−10 recommendation entirely until it
is re-tested with announcement-weekday held fixed. P1's grade change from
ASSUMED to MEASURED-ON-COST / PENDING-NET is appropriate; the basis line should
cite this audit, not §5 of `EX-2.md`, for the mechanism.

## 13. Log delta

Replays E0025–E0048 (24, verbatim, identical output). New spec-wiggle probes
E0049 `dte_true→cost_ic` +0.13482; E0050 `n_strikes→cost_ic` −0.07807;
E0051 `n_strikes→spread` +0.46548; E0052 `entry_mid→cost_ic` +0.03774;
E0053 `entry_mid→spread` +0.77397. Log now 53 entries. All ad-hoc pandas work in
§2–§9 is AUDIT-DIAGNOSTIC and **not promotable**.
