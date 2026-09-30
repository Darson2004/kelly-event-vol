# LOCKED REGISTRY — Stage B4, 2026-09-01

Family size m=6. BH-FDR q=0.10 (lone survivor needs p ≤ 0.0167). Statistic:
within-season permutation p (harness v3, `--pvalue perm`), on the SEALED
small-cap validation set (`lockbox/validation_smallcap.csv`, n=750,
seasons 2025Q3+, opened once at Stage B5 with LOCKBOX_OPEN=1 after explicit
human sign-off, "OPEN THE LOCKBOX"). Correct pre-registered sign required. All six
outcomes will be reported, pass or fail. No re-tuning after opening — ever.

Registered from discovery-stage evidence (all FRAGILE/candidate-grade; see
notes/ and audit reports in the research log). Exact commands:

R1  H7-pure  (recency anchoring, level-cancelled; discovery honest p≈0.065, sign + in every season slice)
    test --data lockbox/validation_smallcap.csv --feature ratio_last_rm/ratio_avg_rm --target tail --hyp R1 --sign + --pvalue perm

R2  H7-raw   (recency anchoring, raw ratio; discovery honest p≈0.035)
    test --data lockbox/validation_smallcap.csv --feature ratio_last_rm --target tail --hyp R2 --sign + --pvalue perm

R3  H1-tail  (cheap vs own implied history; unresolvable in discovery due to
    coverage degeneracy — validation slice is late-panel where snapshot
    coverage is maximal)
    test --data lockbox/validation_smallcap.csv --feature ratio_avg_im --target tail --hyp R3 --sign - --pvalue perm

R4  H1-ic    (same feature, rank channel)
    test --data lockbox/validation_smallcap.csv --feature ratio_avg_im --target ic --hyp R4 --sign - --pvalue perm

R5  H2-flip  (event-share inversion, NEW registration with mechanism "event
    share is itself a price"; discovery tail t=-3.15 but that estimate is
    contaminated-by-selection — this is its first clean test)
    test --data lockbox/validation_smallcap.csv --feature im_entry/iv_amb_entry --target tail --hyp R5 --sign - --pvalue perm

R6  ABS-ic   (absolute cheapness head-to-head partner for R3/R4, per the H1
    audit's re-pose: does relative-to-history beat absolute level?)
    test --data lockbox/validation_smallcap.csv --feature im_entry --target ic --hyp R6 --sign - --pvalue perm

NOT registered (with reasons): H3/H6 (decompose into one premium/ambient
factor + the H9 cost artifact; zero incremental evidence), H4 (month ≡
season in a one-cycle panel), H5 (net channel is cost accounting; gross
anomaly recorded, untradeable by construction), H9/H10 (controls).
