# Execution pack — issue tracker

Status vocabulary: **OPEN** · **RESOLVED** · **QUOTED** (awaiting a spend
decision) · **WONTFIX** (recorded so it is not re-proposed).

---

## AMEND-1 — dead staleness detector, and a hole in guard G1 · **RESOLVED**

*Found tick 1 by the EX-2 runner; diagnosed by the EX-2 auditor.*

**Problem.** `stale_dd` was identically 0.0 across all 4,778 non-null rows.
It required exact four-way float equality of `call_bid`, `call_ask`,
`put_bid`, `put_ask` against the prior session. Measured read-only on
518,008 real contract-days, the true rates are: per-leg unchanged 1.07%,
≥1 leg 3.37%, all four **0.019%** — so the detector's expected firing count
over the whole panel was **~0.9**. A reading of 0/4778 was equally
consistent with "no staleness" and "not looking."

Worse, the G1 semantic assertion (`set(unique) ⊆ {0,1}`) is *satisfied* by
an all-zeros column. **A dead detector passed the semantics gate**, which
is precisely the failure G1 exists to prevent, one level up.

**Fix.**
1. `stale_dd` → four real detectors: `stale_legs` (graded 0–4),
   `stale_econ` (mid unchanged while spot moved ≥0.5% — economically
   impossible, therefore a carried-forward mark), `book_bad` (zero/absent
   bid, or crossed/locked), `spread_vs_own` (entry spread vs the contract's
   own trailing median).
2. G1 strengthened with a `NON_DEGENERATE` class: any column whose guard
   depends on it firing must have `nunique() > 1`. A domain assertion alone
   cannot distinguish clean data from an absent measurement.
3. Selftest 7 → 11 checks, including a **regression test for this exact
   defect**: an all-zeros detector must now FAIL semantics.

**Verification.** Selftest 11/11 PASS. Panel rebuilt (v2, identical
coverage: 4,835 rows / 967 events / 42 tickers), semantics 10/10 PASS.
Detectors now fire: `stale_legs` ≥1 on **3.47%** of entries — which
independently matches the auditor's 3.37% measurement from the raw chains —
`stale_econ` 31 fires, `book_bad` 5 fires.

**Residual, recorded not hidden.** `stale_legs` only ever takes 0 or 1 on
this universe; no entry has two or more legs unchanged. The graded scale is
kept because it is the honest measurement, but it behaves as binary here.

**Unblocks:** EX-3. v1 panel retained and hashed so every tick-1 number
stays reproducible. Freeze record: `FREEZE.txt` amendment A1.

---

## ANOM-2 — EX-5 is arithmetic, not an experiment · **WONTFIX (by design)**

`cmd_build` computes `exit_mid` once per event, outside the lead loop
(verified: 0 of 967 events have more than one distinct `exit_mid`). This is
correct — every lead exits at the same pre-print mark. The consequence is
that paired gross difference is a deterministic function of the entry mids
EX-2 already published:
`gross_a − gross_b = exit_mid·(mid_b − mid_a)/(mid_a·mid_b)`.

So "which lead maximises net" is a **calculation, not a test**. EX-5 is
re-scoped to spend no alpha and spawn no runner. Recorded as a standing
protocol lesson: some execution questions are closed-form, and a pipeline
that pays alpha for them is buying nothing.

---

## ANOM-3 — weekday/lead collinearity · **OPEN (assigned to EX-7)**

`ann−7` and `ann−14` fall on the announcement's own weekday; T−3/T−5/T−10
are ~65% Friday. This already manufactured one false finding (the T−10
saving, now POLICY P7 REFUTED — negative in 1 of 5 weekday strata,
weekday-adjusted p=0.771). Realised mean leads are 3.98/5.43/7.03/11.01/
14.05, so nominal bucket labels also misstate step sizes, which produced the
withdrawn convexity claim.

**Rule now binding:** no lead comparison may be run without holding
announcement weekday fixed. Encoded as POLICY standing limitation 2 and as
hypothesis EX-7.

---

## BLOCK-1 — P2 "mid-or-better fills only" is untestable · **QUOTED**

**The framing was wrong and is corrected here.** I originally scoped this as
"buy intraday quotes." Quotes cannot test a fill assumption — knowing where
you *would* have filled requires **trade prints with quote context at trade
time**. On OPRA that is the `tcbbo` schema.

**Schema availability (verified against the API, not assumed).**
`OPRA.PILLAR` does **not** support `tbbo` or `mbp-1`. Supported:
`cmbp-1`, `cbbo-1s`, `cbbo-1m`, `tcbbo`, `trades`, `ohlcv-*`, `statistics`,
`definition`. History limits observed while pricing: `cbbo-1m` and `trades`
priced successfully back to 2021; `tcbbo` and `cmbp-1` returned
`data_schema_not_fully_available` before ~2023; `cbbo-1s` failed before
~2025.

**Quote** (`metadata.get_cost`, nothing downloaded or billed; cost per
symbol-day sampled, scaled by plan symbol-days). Plan A = T−14 entry +
pre-print exit dates (881 days, 1,934 symbol-days). Plan B = all five
candidate leads + exit (1,309 days, 5,395 symbol-days).

| schema | $/sym-day | Plan A | Plan B | 200-event pilot | history | answers |
|---|---|---|---|---|---|---|
| **`tcbbo`** | 0.459 | **$888** | $2,478 | **$184** | 2023+ | **P2 fill realism** — where trades print vs the NBBO |
| `trades` | 0.632 | $1,223 | $3,411 | $253 | 2021+ | prints only, no quote context — needs a lossy join |
| `cmbp-1` | 0.678 | $1,311 | $3,657 | $271 | 2023+ | P2 + depth/queue |
| `cbbo-1s` | 2.257 | $4,365 | $12,177 | $903 | ~2025+ | second-resolution timing |
| `cbbo-1m` | 0.110 | **$214** | $596 | $44 | 2020+ | full-session intraday timing (no fills) |

Estimates carry real dispersion — `tcbbo` per-symbol-day samples ranged
$0.14–$0.75 across 4 usable days, so the $184 pilot is plausibly $60–$300.
Treat the table as an order of magnitude, not a contract.

**Recommendation: buy the $184 `tcbbo` pilot first.** ~200 stratified
events × entry+exit days answers, with ample power, the question the whole
strategy rests on — do options in these names actually trade at mid, and
how does that degrade with spread width, lead, and name? Only after that
result should the $888 full-panel `tcbbo` or the $214 `cbbo-1m` timing
dataset be considered. Do not buy `cbbo-1s`.

**Status: awaiting the spend decision. Nothing has been purchased.**

---

## BLOCK-2 — intraday timing across full history · **OPEN, not yet needed**

Full-session `cbbo-1m` (Plan A, $214) would unlock time-of-day entry
research (EX-B1) over the entire 2020+ panel, since `cbbo-1m` has the long
history. Deliberately deferred: it answers "when within the day" while P2
answers "does our fill assumption hold at all," and the second question
dominates. Revisit after BLOCK-1 resolves.
