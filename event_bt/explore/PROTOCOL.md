# Exploration Protocol — top-decile signal hunt (frozen 2026-08-31)

*The research question: WHICH pre-earnings events become the big winners that
carry the strategy's P&L (top decile = 36% of |P&L|), and is that
predictable ex-ante? This protocol governs how we explore without
manufacturing false discoveries or lazily declaring "nothing there."
Derived from three meta-research memos (see memos/README.md).*

## 0. The two failure modes and their mechanical countermeasures

| Failure | Countermeasure (mechanical, not aspirational) |
|---|---|
| Premature "nothing there" | Coverage grid with per-cell verdicts; a null verdict is INVALID without ≥3 logged probes + detectable-effect-size statement ("we could have seen X; we saw less") |
| Fabricated/overfit "something" | Evaluator frozen & hashed BEFORE hypothesizing; generator never grades itself (finding-auditor subagent re-runs + tries to kill); every reported number must trace to an experiments.jsonl entry; family-wise BH-FDR with the FULL trial count |

## 1. Data governance (Stage 0 — freeze before looking)

- **Discovery (free exploration):** small/mid-cap trades with ann_date < 2025-07-01
  (~2 of 3 of the ~3,650-event panel) + the historical liquid cell
  (results_liquid_full/T14) which is **already contaminated** (aggregates seen
  2026-08-29) and may be used descriptively only — it can suggest, never confirm.
- **Validation (one shot, sealed):** small-cap trades with ann_date ≥ 2025-07-01,
  written to `lockbox/validation_smallcap.csv` at freeze time and not read by
  any process until Stage 4. Opened once.
- **Transfer corroboration:** the historical liquid cell, sign/rank tests only.
- **True lockbox:** liquid events accruing prospectively from 2026-09 (the
  paper-trade season). Pre-committed evaluation: ~60 events, sign test on
  tail-hit rate conditioned vs unconditioned.
- All frozen files hashed into `SHA256SUMS`; eval harness refuses to run on a
  file whose hash isn't in the manifest.

## 2. Roles (generator/grader separation)

- **Orchestrator (LLM agent):** plans, spawns, reconciles, never computes a
  p-value by hand, never edits `eval_harness.py` after freeze (hash recorded).
- **hypothesis-runner (subagent):** executes probes on DISCOVERY data only,
  via `eval_harness.py`; ≥3 probes per hypothesis cell before any verdict;
  logs every run BEFORE interpreting it; ends every note with a
  hyperresearch-style **committed position + calibration block** (confidence
  bucket / boundary conditions / what-would-flip-this / evidence weight).
  "We don't know" is not a position; "insufficient power to detect < X" is.
- **finding-auditor (subagent, Read+Bash only, fresh context):** for every
  positive finding: re-run the exact logged command, confirm the reported
  number appears in real output, then actively try to kill it — shuffled
  labels, season-drop jackknife (does one earnings season carry it?),
  sign-flip across universes, alternative statistic. Verdict vocabulary:
  REPLICATED / FRAGILE / REFUTED / FABRICATED. Nothing enters the report
  without an auditor verdict.

## 3. The loop (adapted hyperresearch × AIDE)

1. **Perspectives (STORM move):** generate hypotheses as five personas — vol
   dealer (positioning/gamma), regime macro (VIX/rates state), microstructure
   (spread/volume/term-structure shape), behavioral-attention (coverage,
   retail flow, prior-quarter surprise), and skeptic (null mechanics that
   would fake each pattern). Grid = persona × feature family.
2. **Descriptive pass (free, discovery data only):** characterize top-decile
   trades — calendar/season clustering, regime, sector, entry-signal levels,
   implied-move path shape. Output = candidate hypotheses, each written into
   `HYPOTHESES.yaml` with mechanism + predicted SIGN before any validation
   computation. LLM exploration counts toward N (trial log includes it).
3. **Discovery sweep:** cheap rank/sign probes per hypothesis on discovery
   data. Loci scoring (Importance/Uncertainty/Disagreement/Decision-Impact)
   allocates deeper budget to where evidence forks. Tree, not line: dead
   branches die in subagent context; registry keeps score.
4. **Registry lock:** distill to ≤ 8 registered hypotheses (test-budget
   arithmetic: BH q=0.10 at family size ~8 ⇒ lone survivor needs p≈0.012;
   6 years of data affords ~a dozen trials before max-Sharpe-of-noise wins).
   Hash the registry.
5. **Validation (one shot):** run the ≤8 pre-specified tests on the sealed
   small-cap holdout. BH q=0.10 within family; correct sign required; report
   ALL outcomes including failures. No second look.
6. **Transfer:** survivors → sign/rank-only tests on liquid historical
   (corroboration, not proof; expect ~35% attenuation). Compute DSR with
   N = total logged trials; PBO/CSCV with season blocks for anything
   packaged as a rule.
7. **Lockbox verdict:** the prospective liquid season decides capital.

## 4. Statistics (frozen in eval_harness.py)

- **Never means.** Targets: (a) big-winner membership (long_ret_net ≥ +50%,
  fixed ex-ante), (b) Spearman rank-IC vs net return, (c) Wilcoxon/sign on
  median split. Tail-driven P&L makes mean tests uninterpretable at our n.
- **Season-cluster bootstrap-t** (earnings season = year-quarter cluster;
  resample clusters, keep trades together; bootstrap-t not percentile).
- **BH-FDR q=0.10** over the registered family; HLZ minimum Bayes factor
  exp(−t²/2) reported alongside every p.
- **Power floors (from the methodology memo, computed for our n):** liquid
  n≈193 detects only tail-rate doubling (10%→20%) or |ρ|≥0.25; small-cap
  discovery n≈2,400 detects ~10%→13%; anything smaller ⇒ verdict is
  NULL-WITH-POWER, stated as "effect, if any, < detectable X".
- **Verdicts per cell:** SUPPORTED / REFUTED / NULL-WITH-POWER / BLOCKED.

## 5. Reporting standard (Fabozzi–López de Prado disclosure)

Final report must contain: total trial count N (including every agent probe),
family definitions, all negative results with power statements, DSR for any
survivor, auditor verdicts, registry diff history, and a NOT-TRIED section.
A report without negative results is rejected by construction.

## 6. Invocation

The exploration loop (LLM-orchestrated) drives Stages 1–3; Stage 4 requires an explicit
human sign-off ("OPEN THE LOCKBOX") plus `LOCKBOX_OPEN=1`; Stages 5–7 follow only for survivors.
