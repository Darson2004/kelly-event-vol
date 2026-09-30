# Execution Research Protocol — pre-earnings long straddle (frozen 2026-09-01)

*The research question: **when, and whether, to put the trade on.** The
strategy graduated on a backtest that assumed mid-or-better fills at T-14
for every qualifying event. Neither the timing nor the fill assumption has
ever been tested. This pack tests them.*

Driven by the execution-research loop (an LLM-orchestrated tick loop over this frozen pack). Sibling of `explore/` (signal selection);
the two never share a harness, a log, or an alpha budget.

## 0. Why this is a different machine from the signal pack

| | signal research (`explore/`) | execution research (here) |
|---|---|---|
| Dependent variable | realized P&L | realized **cost** and paired policy differences |
| Signal-to-noise | terrible (tail-driven, median trade −4.9%) | good (costs are persistent and repeat) |
| Counterfactual | unobservable | **observable** — the same event entered on another day |
| Confounding | severe (regime, season, name) | mostly removed by within-event pairing |
| Validation | one sealed split, one shot | **each new earnings season**, forever |

That last row is what makes a continually-running loop legitimate here and
illegitimate there.

## 1. Data governance

- **Panel:** `panel_liquid.csv` — one row per (event × entry lead), built by
  `exec_harness.py build` from `data/canonical_liquid/`. 4,835 rows, 967
  events, 42 tickers, leads {3,5,7,10,14}, seasons 2020Q4–2026Q3. Hashed in
  `SHA256SUMS`; the harness refuses any panel not matching its hash.
- **Quote reality (binding limitation):** the underlying Databento cbbo-1m
  cache holds **4 one-minute bars per day, 15:44–15:47 ET, bid/ask only, no
  sizes**. Therefore: daily entry-day choice, executability screening and
  mark-staleness ARE researchable; **intraday timing, queue position and
  depth are NOT**, and no hypothesis about them may be queued until new data
  is purchased. Every mark in this panel is a near-close mark.
- **Prospective holdout:** events after the pack's freeze date accrue
  naturally. A hypothesis graduates to POLICY only after confirmation on a
  season that did not exist when it was registered. Any panel file whose
  name contains `holdout` is sealed behind `EXEC_HOLDOUT_OPEN=1`.
- Nothing in this pack ever places an order, moves money, or fetches paid
  data. Data purchases are escalated for a human spend decision, never executed by the loop.

## 2. The four execution-specific guards

Each is a mechanical countermeasure to a failure this project actually hit.

**G1 — Semantics before statistics.** Every column carries a machine-checked
assertion in `SEMANTICS`; a column that fails cannot be graded. *Origin: the
signal pack spent a full probe-and-audit cycle on `dte_entry`, which was
named days-to-expiry and was actually `(ann_date − entry_date)`. The
registered mechanism was refuted because the variable was not the variable.*

**G2 — Never grade a cost hypothesis on net P&L.** Net return contains the
cost term, so a cost feature "predicting" net return is partly arithmetic.
Cost hypotheses are graded on `cost_frac`; policy choices report cost, gross
and net **separately**. *Origin: H11 scored IC +0.21 on net and +0.09 on
gross, and the long and short legs of the same straddle ranked together at
+0.46 — the ranking was dominated by a shared cost term.*

**G3 — Screens are graded on both sides.** `admit` always reports admitted
fraction, cost saved AND foregone gross-tail events. A screen that lowers
average cost while discarding the fat right tail destroys a strategy whose
top decile is ~36% of |P&L|. *Origin: the standing anomaly that high-spread
small-caps carry ~3× the gross tail rate, exactly consumed by costs.*

**G4 — A quote that does not move is not a price.** `stale_dd` flags entries
whose quote is identical to the prior session's. Cost and return numbers
computed off stale marks are marks, not fills, and any finding resting on
them is provisional until the staleness rate of its subsample is reported.

## 3. Roles

- **Orchestrator (LLM agent):** runs the tick, never computes a statistic
  by hand, never edits the harness or the panel mid-tick.
- **hypothesis-runner (subagent):** probes one queued hypothesis via the
  harness; ≥3 logged probes; ends with a committed position + calibration
  block. Paired `policy` evidence outranks cross-sectional `test` evidence.
- **finding-auditor (subagent, fresh context):** every CANDIDATE is audited
  before promotion — replay from the log, season jackknife, staleness
  stratification, G2 circularity check, G3 both-sides check, hidden-trial
  count. Verdicts REPLICATED / FRAGILE / REFUTED / FABRICATED.

## 4. Statistics (frozen in exec_harness.py)

- **Paired sign-permutation** on within-event differences is the primary
  test (`policy`). Assumption-free, heavy-tail safe, and the pairing removes
  event/name/season confounding by construction.
- **Cluster bootstrap CI** with the effective-cluster count printed; below 4
  clusters the CI is declared untrustworthy and only the permutation p is
  admissible. *Origin: the signal pack's cluster bootstrap overstated
  significance ~100× at 2–3 effective clusters.*
- **Rank statistics only** for cross-sectional work; never means.
- Medians, not means, for every cost and return summary.

## 5. Sequential alpha budget (what makes a forever-loop honest)

A pipeline that tests indefinitely will eventually find noise. Total
family-wise budget **α = 0.10**, spent on a convergent schedule:

    α_k = α · 6/(π²k²)     →  k=1: 0.0608, k=2: 0.0152, k=3: 0.0068,
                              k=4: 0.0038, k=5: 0.0024, …  Σ = α

A discovery result at tick *k* is promotable to CANDIDATE only at
`p ≤ α_k`. The budget is tracked in `STATE.json` and never reset. Spent
budget is not recovered by abandoning a hypothesis — abandoned probes still
count, as in the signal pack.

Graduation to POLICY additionally requires **prospective confirmation**: the
correct sign on a season that did not exist at registration time. That test
costs no discovery alpha, because it is genuinely out of sample.

## 6. Promotion ladder

    QUEUED → PROBED → AUDITED → CANDIDATE → PROSPECTIVE → POLICY
                          ↓
                     CLOSED (with power statement)

Demotion is symmetric: a POLICY rule that fails two consecutive prospective
seasons returns to CANDIDATE and is removed from `POLICY.md` in the same
tick.

## 7. Reporting standard

Every tick ends with: FINDINGS (auditor verdict + entry ids) ·
NEGATIVE_RESULTS (with power statements) · POLICY_DELTA (what changed in
`POLICY.md`, or "none") · BUDGET (α spent this tick, α remaining) ·
NOT_TRIED · ANOMALIES · TRIAL_COUNT (tick and cumulative).
