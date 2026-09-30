# Iteration 2 — discovery loop, 2026-09-01

Second exploration pass on the pre-earnings long-straddle signal question.
Registry R1–R6 remained LOCKED throughout; `lockbox/` never touched.
Harness verified before probing: sha256 `156e331911c3…` = FREEZE.txt v3,
selftest 6/6 PASS.

Trial ledger: log went 48 → 85 entries (37 new: 34 probes + audit replays).
Cumulative N = 85 across both iterations.

## Cell verdicts

| Cell | Feature | Runner verdict | Auditor | Standing |
|---|---|---|---|---|
| H11 | `ratio_avg_im/ratio_avg_rm` | SUPPORTED (ic) | **FRAGILE** | not promotable |
| H12 | `dte_entry` | SUPPORTED (ic+median) | **FRAGILE** | not promotable; feature misnamed |
| H13 | `n_prior_rm` | NULL-WITH-POWER | n/a | closed |
| H14 | `ratio_last_im/ratio_avg_im` | NULL-WITH-POWER | n/a | closed, informative for R1/R2 |

Both SUPPORTED verdicts replayed bit-exact (H11 9/9, H12 5/5). No
fabrication in either. Both were nonetheless refused promotion.

## What survived and what it means

**H11 → the factor is not what was hypothesised.** The depth confound the
runner nominated as decisive failed to kill it (within-stratum ICs +0.156 /
+0.117, partial +0.149), ticker structure clean (350 tickers, max 0.6%).
But the audit's decomposition collapses the whole family — H11 ratio,
`ratio_avg_rm`, and variants — onto one raw quantity: **the name's average
prior realized earnings move** (IC +0.206, n=695). `im_entry` contributes
nothing (IC −0.013). Blocking objections: footprint is 2025Q1–Q2 ONLY (the
runner's stated 2024Q2–2025Q2 was wrong; zero coverage of 62 of 79 panel
winners, so its own flip-condition was vacuous); ~half the net effect is a
relative-spread proxy (net IC +0.21 vs gross +0.09; long/short legs of the
SAME straddle rank together at +0.46 ⇒ common cost term); and the top
decile holds 0 of 47 winners — a loss-mitigation ordering, not a tail
selector. Multiplicity: Bonferroni on honest p = 0.067, fails.

**H12 → the feature was a pipeline artifact.** The association is unusually
robust (survived season jackknife, gross-return check, event-share control,
theta/hold control, ticker concentration, and a within-date permutation at
p=0.0065 that removes all calendar confounding — every control made it
*stronger*). But `dte_entry` is not days to expiry: it is
`(ann_date − entry_date).days` on 2892/2892 rows, i.e. the **T-14
entry-date snap indicator**. True dte is null (IC +0.0148, wrong sign).
Snapped-vs-off rows differ enormously in companion-data missingness
(`im_entry` 58.3% vs 29.9% missing), so the leading explanation is
**entry-mark quality on a sparse/stale chain** — a gross-level artifact that
`spread_frac_entry` cannot capture. Net effect rests on 30 complete-data
trades.

**H14 → strengthens the locked R1/R2.** The implied-side algebraic twin of
H7's recency ratio shows nothing (4/4 wrong-signed, n=474, best p=0.36)
while the realized side benchmarks at +2.04pp (X0034). The
construction-artifact alternative for R1/R2 failed to reproduce; read R1/R2
as realized-move-specific anchoring. Caveat: at n=474 an H7-sized effect is
near the power floor, so this leans on sign agreement, not p-values.

**H13 → closed.** Median split was a 2024-vs-2025 calendar split; the column
is panel tenure (0–4), not option-history age. Within-season: nothing.

## Consequences recorded elsewhere

1. `FREEZE.txt` — DISCLOSED LIMITATION (harness unchanged): perm p is floored
   at 1/2001 = 0.0005 and `cmd_test` inverts the floored p to produce
   `t_boot`/`mbf`, so every floor-hitting probe prints an identical
   t=3.48 / MBF=0.0023. Resolution artifact, not an estimate. Stage-5 reads
   must treat floor results as "p ≤ 0.0005" and must not quote printed t/MBF
   as magnitudes. BH-FDR ordering unaffected. `n_perm` deliberately NOT
   raised — that would alter the frozen grader before the lockbox opens.
2. `HYPOTHESES.yaml` — H12 correction block appended (feature misnamed,
   mechanism refuted); original text left intact for trial-record integrity.

## Open items for the next loop (NOT tried here)

- Test the surviving factor honestly: **average prior realized earnings
  move** on a GROSS-return leg with an explicit spread control, on
  `ratio_last_rm` (n=1340, 578 events in 2024Q4) to escape the 2025H1
  footprint.
- Verify whether the entry-snap condition is knowable at entry; if so the
  operational rule needs no registry slot — *if the T-14 entry cannot be
  struck on schedule, skip the event rather than entering off-schedule.*
- Check whether snapped-row entry premia are stale marks (would explain H12
  entirely and is a data-quality fix, not a signal).
- Whether the live liquid screen's numerator (`im_entry`) carries signal in
  the LIQUID panel — the small-cap decomposition says it does not here.

## Registry status

**No re-lock.** Both auditors recommended against it. R1–R6 stand exactly as
locked on 2026-09-01; sealed validation still awaits the explicit one-shot
sign-off ("OPEN THE LOCKBOX").
