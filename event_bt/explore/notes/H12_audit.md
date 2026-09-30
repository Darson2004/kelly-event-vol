# H12 audit — finding-auditor (fresh context, adversarial)

**Feature:** `dte_entry` · **Data:** `data/discovery_smallcap.csv` (sha b80d380463d7c8f9)
**Runner verdict:** SUPPORTED (ic + median), tail NULL-WITH-POWER.

## VERDICT: FRAGILE

The *statistic* replicates and survives every kill-test I could build.
The *mechanism* is refuted: `dte_entry` is not days-to-expiry.

---

## 1. Reproduce — PASS (all five cited probes, exact match)

Replayed the logged command strings verbatim. New log ids appended (X0070–X0074).

| cited | replay | stat | t | p | MBF | match |
|---|---|---|---|---|---|---|
| X0050 tail perm | X0072 | −0.01377 | −0.34 | 0.73263 | 0.9433 | exact |
| X0053 ic perm | X0070 | −0.05853 | −3.29 | 0.00100 | 0.0045 | exact |
| X0057 median perm | X0071 | −0.09987 | −2.92 | 0.00350 | 0.0141 | exact |
| X0065 ic boot | X0073 | −0.05853 | −3.08 | 0.00600 | 0.0088 | exact |
| X0067 median boot | X0074 | −0.09987 | −5.75 | 0.00027 | 0.0000 | exact |

Every descriptive number in the note also reproduces (bucket medians net
−0.1257/−0.1840/−0.2822; gross +0.0430/0.0000/−0.1022; spread
0.3378/0.2908/0.3436; im 0.1032/0.0981/0.0733; iv_amb 0.4848/0.5199/0.6330;
winners 4/74/1; 2764 at dte=14; 67 of 72 in 2025, 32 in May-2025).
**No fabrication.**

## 2. Season jackknife — SURVIVES

| drop | n | IC | median gap | n_hi left |
|---|---|---|---|---|
| 2024Q2 | 2884 | −0.0581 | −0.0999 | 70 |
| 2024Q3 | 2012 | −0.0606 | −0.0999 | 71 |
| 2024Q4 | 1966 | −0.0757 | −0.1102 | 70 |
| 2025Q1 | 2233 | −0.0442 | −0.0814 | 52 |
| **2025Q2** | 2473 | **−0.0611** | **−0.1144** | 25 |

Dropping 2025Q2 (the 32 May-2025 trades) leaves the IC *stronger* than full
sample. Two seasons carry it independently (2025Q1 IC −0.101, n_hi=20;
2025Q2 IC −0.111, n_hi=47). Leave-one-*date*-out: worst case moves the
median gap only from −0.0999 to −0.0912. Not a one-season artifact.

## 3. Specification wiggle — consistent; tail genuinely null

Gross channel (removes cost accounting): IC −0.0668, median gap −0.1022 —
*stronger* than net. Delta-hedged variants −0.0550 / −0.0636. Short side
flips sign as it should (+0.0744 net gap). Tail target null (−1.4pp,
p=0.733) as the runner disclosed. No sign flip anywhere on the long side.

## 4. Confounds — all fail to kill

- rank corr(dte, spread_frac_entry) = **−0.0055** (spread IC vs net is −0.49,
  the dominant mechanical driver — dte is orthogonal to it).
- Partial Spearman(dte, net | spread, prem, spot, iv_amb) = **−0.0653**.
- Stratified by iv_amb decile: **−0.0711**. By event-share decile: **−0.0714**.
- Ticker concentration: 72 trades / **71 distinct tickers**, max 2 (2.8%).
- **Within-ann_date** (removes every date-level confound — regime, market
  move, season, "it was May 2025"): demeaned rank IC **−0.1157**,
  within-date permutation p = **0.0065**; date-level sign test 16 of 19
  dates negative, p = 0.0022. Ann_date-cluster bootstrap: t = −2.99,
  p = 0.0010.
- H2/R5 costume test: the >14 bucket has *low* event share (0.138 vs 0.208),
  and per H2 low event share predicts **better** outcomes — H12 runs against
  H2, not with it. Not H2 in calendar costume.
- Theta / hold-length (the runner's own skeptic flag): hold length's own IC
  is **+0.041** (wrong sign); partial Spearman(dte, net | hold) = **−0.0744**;
  within hold==14 rows (n=1442, 37 hi) IC = −0.0644, gap −0.1066. Theta dead.
- Full joint control (hold + true-dte + spread + prem + spot + iv_amb):
  **−0.0850** net, **−0.0755** gross. Every control makes it stronger.

## 5. Mechanism — REFUTED

`dte_entry` equals `(ann_date − entry_date).days` for **2892/2892 rows**
(exact identity). It is **not** days to expiry: `dte_entry == expiry_post −
entry_date` matches 0.31% of rows. All 2764 rows at dte=14 have entry weekday
== announcement weekday; **all 128 off-tie rows have entry weekday ≠
announcement weekday**. `dte_entry` is the *entry lead* / T-14 date-snap
indicator, not an expiry-grid variable.

The variable the hypothesis actually describes is `expiry_post − entry_date`
(true days-to-expiry, range 14–60, median 24). It is **null**:

| true dte | n | net med | gross med | winner rate |
|---|---|---|---|---|
| 14–20 | 555 | −0.1776 | −0.0214 | 3.96% |
| 21–25 | 1124 | −0.1992 | +0.0325 | 3.65% |
| 26–30 | 534 | −0.2031 | −0.0343 | 0.94% |
| 31+ | 679 | −0.1483 | +0.0039 | 1.62% |

IC = **+0.0148** (wrong sign), median-split gap **+0.027**, tail gap −0.016.
True dte *does* carry the dilution covariate gradient (im 0.107→0.081,
iv_amb rising) — so the predicted fingerprint is present and produces no
return effect.

Two structural claims in the note are false: the >14 bucket is **not**
"expiry 1–4 days past the event" (`expiry_post − ann_date` there spans 0–44
days, modes 9 and 29), and the panel **does** contain true monthlies (679
trades at 31+ true dte). "No 30–45 dte in this panel" is incorrect.

## 6. Effective-n and data quality

The >14 bucket is a data-sparse stratum: `im_entry` missing **58.3%** vs
29.9% elsewhere, `iv_amb_entry` 27.8% vs 3.1%, `amb_rv_hold` 26.4% vs 0.7%,
`short_ret_*` 41.7% vs 17.5%. Splitting on data completeness:

| stratum | n | n_hi | net gap | gross gap |
|---|---|---|---|---|
| complete im_entry | 2004 | 30 | **−0.1324** | −0.0965 |
| missing im_entry | 888 | 42 | **−0.0112** | −0.1321 |

The headline *net* penalty rests on **30 trades**. The gross effect is
present in both strata, which is why the association survives controls.
Distribution shape in the >14 bucket is compression, not uniform drag:
q10 −0.514 (vs −0.620 at dte=14) but q90 −0.003 (vs +0.191) — upside
truncated, which is why the +50% tail probe is directionally right (1/72)
and hopelessly underpowered.

## 7. Trial-count honesty — PASS

`experiments.jsonl` holds exactly **5** H12 entries pre-audit (X0050, X0053,
X0057, X0065, X0067); the note reports all five, including the failing tail
probe. No abandoned variants, no hidden family, no post-hoc sign — H12 was
written into HYPOTHESES.yaml with sign "-" before any iteration-2 probe.
Total log: 69 pre-audit (74 after my replays); iteration-2 window = 21 probes
across H11–H14.

Minimum Bayes factor at the claimed p, posterior odds at a 1:9 prior:

| family m | Bonf p | z | MBF (BF01) | BF10 | posterior |
|---|---|---|---|---|---|
| 1 (as reported) | 0.0010 | 3.29 | 0.0045 | 224 | 24.9:1 (96%) |
| 3 (H12 targets) | 0.0030 | 2.97 | 0.0122 | 82 | 9.1:1 (90%) |
| 12 (iter-2 pre-registered) | 0.0120 | 2.51 | 0.0426 | 23 | 2.6:1 (72%) |
| 69 (full log) | 0.0690 | 1.82 | 0.1914 | 5.2 | 0.6:1 (37%) |

m=12 is the fair family (four pre-registered iteration-2 cells x three
targets): **~72% posterior**, and it passes BH q=0.10 at any m up to 69.

## 8. Strongest surviving alternative explanation

The T-14 entry date was unusable for these 128 events and the pipeline walked
to a neighbouring session — and the walked rows are demonstrably the
thin-chain rows (58% no implied move, 28% no ambient IV). The most likely
economic content of `dte_entry` is therefore **entry-mark quality on a
sparse or stale option chain**: an entry premium struck off a stale mid is
biased high, which depresses `long_ret_gross` mechanically. This survives the
runner's gross-return defence, because a stale *mark* is a gross-level
artifact rather than a cost-level one, and it is not captured by
`spread_frac_entry` (staleness is not width). I could not fully separate it
from a real effect: the association persists inside the complete-data
stratum (gross gap −0.0965, n_hi=30), which argues against pure staleness,
but 30 trades cannot settle it.

## 9. Promotability

**Not promotable as written.** The registered mechanism (expiry overhang to
event-share dilution) is refuted by the correct variable being null; the
surviving effect belongs to a misnamed column whose economic content is
unidentified. Before registry consideration it needs (a) the note and the
HYPOTHESES.yaml H12 text corrected to "entry-date snap", (b) a disclosed
re-lock registering the *entry-lead* feature with an entry-mark-quality
mechanism and a pre-committed sign, (c) a check that the snap condition is
knowable at entry (it is a pipeline state, not a market state), and (d)
confirmation that the entry premium on snapped rows is not stale. As a
purely operational conclusion it is already actionable and needs no registry
slot: **if the T-14 entry cannot be struck on schedule, skip the event
rather than entering early or late.**

---
*Sections 2–6 and 8 are AUDIT-DIAGNOSTIC read-only pandas on the frozen CSV —
not harness output, never promotable. Section 1 numbers are the only official
statistics in this file.*
