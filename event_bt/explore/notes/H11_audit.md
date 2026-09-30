# AUDIT — H11 (`ratio_avg_im/ratio_avg_rm`, predicted sign +)

Auditor: finding-auditor subagent, fresh context, Read+Bash only.
Data: `data/discovery_smallcap.csv` sha `b80d380463d7c8f9...` (matches SHA256SUMS).
Harness sha `156e331911c37a30...` = the v3 hash recorded in FREEZE.txt. No edits made.

## VERDICT: **FRAGILE**

Not FABRICATED (every cited number replays bit-exact), not REFUTED (the kill test
the runner himself nominated as decisive — depth stratification — fails to kill),
but not REPLICATED either: the finding's stated footprint is wrong by three
seasons, roughly half the net-return effect is a trading-cost proxy, and the
signal's own top decile contains zero big winners.

## 1. Replay — numbers match: YES (9 of 9)

| note cites | replay entry | stat | t | p | n | match |
|---|---|---|---|---|---|---|
| X0051 tail perm | X0076 | 0.00844 | 0.36 | 0.71564 | 474 | exact |
| X0054 ic perm | X0075 | 0.15264 | 3.48 | 0.00050 | 474 | exact |
| X0056 median perm | X0077 | 0.04705 | 2.41 | 0.01599 | 474 | exact |
| X0060 n_prior_im tail | X0081 | -0.00547 | -0.02 | 0.98501 | 2892 | exact |
| X0062 n_prior_im ic | X0078 | 0.13298 | 3.48 | 0.00050 | 2892 | exact |
| X0066 ratio_avg_rm ic | X0079 | -0.21714 | -3.48 | 0.00050 | 695 | exact |
| X0068 ratio_avg_rm tail | X0080 | -0.00283 | -0.00 | 1.00000 | 695 | exact |
| X0069 ratio ic boot | X0082 | 0.15264 | 22.71 | 0.00026 | 474 | exact |
| X0002 numerator ic (-0.055) | X0083 | -0.05546 | -9.68 | 0.00026 | 474 | exact |

No fabrication. The note's descriptive `describe` medians were not re-derived
(free command, no entry id) but are not load-bearing.

**Caveat the note does not state:** the perm p is floored at 1/(n_perm+1)=0.0005
and the harness *inverts the floored p* to produce `t_boot` and `mbf`. So
"t=3.48, MBF=0.0023" is a resolution artifact, identical for X0054, X0062, X0066
and my X0084 — it is not an estimated statistic. The honest normal-theory t at
IC=0.15264, n=474 is **3.32**; an independent ticker-cluster bootstrap gives
SE=0.0464, **t=3.29**, 95% CI [0.063, 0.243].

## 2. KV1 — depth stratification (the decisive test): FAILS TO KILL

The H11 ratio exists only where `n_prior_im` is in {2,3,4} — 350 / 123 / 1 events.
The panel-wide n_prior_im IC of +0.133 is driven by the 0-and-1 vs 2+ contrast,
which lies **entirely outside** the H11 footprint. Within-footprint:

- n_prior_im=2: IC = **+0.1562** (n=350)
- n_prior_im=3: IC = **+0.1168** (n=123)
- n-weighted within-stratum IC = **+0.146** (vs pooled +0.1526)
- rank-partial IC(H11, net | n_prior_im) = **+0.1492**
- spearman(H11, n_prior_im) = +0.0935 (weak)

Nothing collapses below 0.05. **The runner's flagged coverage/depth confound is
dead.** Also: the covered subsample is not "favorably selected" for winners — its
base rate is 1.7% vs the panel's 2.7%.

## 3. KV2 — decomposition: the note's comparison is footprint-confounded, and both candidates are repackagings of one raw variable

On the **common n=474** footprint (like-for-like):

| feature | IC (n=474) |
|---|---|
| H11 ratio | +0.1526 |
| ratio_avg_rm | **-0.1540** |
| ratio_avg_im | -0.0555 |
| im_entry | -0.0207 |

|IC| is essentially **equal**, not "-0.217 beats +0.153". The -0.217 figure is on
ratio_avg_rm's own wider 695 footprint, where the extra 221 events happen to be
stronger (IC -0.292 there). spearman(H11, ratio_avg_rm) = -0.777; partial ICs are
symmetric and small (H11 given rm = +0.053; rm given H11 = -0.057). Neither
dominates on equal data.

**The real decomposition** is one level down. Reconstructing
avg_rm = im_entry/ratio_avg_rm (the name's average prior *realized* earnings
move) and avg_im likewise, H11 = avg_rm/avg_im exactly, and:

- spearman(H11, **avg_rm**) = **+0.847**; spearman(H11, avg_im) = -0.059
- IC(avg_rm) = +0.1487 (n=474) — essentially all of H11's +0.1526
- IC(avg_im) = +0.0239; IC(im_entry) = -0.0207 (n=474), -0.0130 (n=695)
- partial IC(H11, net | avg_rm) = +0.051; given avg_rm and avg_im = **+0.025**
- Harness probe **X0084**: `im_entry/ratio_avg_rm` (= avg_rm) gives IC **+0.20599**,
  n=695, perm p=0.0005 — larger than either registered object, on wider coverage.

So the mechanism the note settles on — "im_entry below ~0.96x the name's average
prior realized move", i.e. *current* implied cheapness — is **also wrong**:
im_entry carries no signal at all (IC -0.013 on n=695). What is left is a single
univariate factor: **the name historically makes large earnings moves**. That is a
volatility-level factor, not a variance-risk-premium-gap factor. The
im-cancellation debate is moot because im_entry was never contributing.

## 4. KV3 — season jackknife: survives, but the stated footprint is WRONG

| season | panel n | panel winners | H11 n | ratio_avg_rm n |
|---|---|---|---|---|
| 2024Q2 | 8 | 0 | 0 | 0 |
| 2024Q3 | 880 | 36 | **0** | **0** |
| 2024Q4 | 926 | 26 | **2** | **2** |
| 2025Q1 | 659 | 7 | 247 | 431 |
| 2025Q2 | 419 | 10 | 225 | 262 |

Drop-one-season IC: drop 2024Q4 = +0.1564; drop 2025Q1 = +0.1626 (n=227);
drop 2025Q2 = +0.1501 (n=249). Season-only: 2025Q1 +0.157, 2025Q2 +0.172.
No single season carries it *among the seasons it has*.

But the note's boundary condition "discovery small-caps **2024Q2-2025Q2**" is
materially false: **the finding lives in 2025Q1-2025Q2 only**, two consecutive
quarters, 472 of 474 events. It has zero coverage of the 62 of 79 panel winners
that occurred in 2024Q3/Q4. The note's own what-would-flip-this item (b) —
"season-drop jackknife killing the IC when 2024Q3 (36 of 79 winners) is removed"
— is **vacuous**: 2024Q3 contributes zero events, so that test can never fire.
Consequently the "it was 2025H1" regime alternative **cannot be tested with these
data**, and the two seasons in question are precisely the low-winner-rate half of
the panel (1.1% and 2.4% vs 4.1% and 2.8%). This alone caps the verdict at
FRAGILE.

## 5. KV4 — ticker concentration: clean, fails to kill

350 distinct tickers in n=474; max single ticker = AGX at 3 events (0.6% share);
mean 1.35 events per ticker. Drop top-1 = +0.1561; top-3 = +0.1520; top-5 =
+0.1471; top-10 = +0.1388. Ticker-cluster bootstrap (2000 reps): SE 0.0464,
t=3.29, 95% CI [0.0628, 0.2429], excludes zero. No concentration problem.
Within-ticker demeaning is uninformative at 1.35 obs/ticker and is not used.

## 6. KV5 — winner-tail honesty: worse than the note admits

The subsample contains **8 winners total**. Their H11 percentiles are
0.08, 0.23, 0.41, 0.50, 0.50, 0.56, 0.68, 0.85 — approximately uniform, median
0.50. Consequently:

- **Top decile by H11: 0 of 47 winners.** Bottom decile: 1 of 47.
- Median split: hi 5/237 (2.11%) vs lo 3/237 (1.27%) — the +0.84pp of X0051.
- Both halves lose money: mean net **-8.9%** (hi) vs **-15.0%** (lo);
  sum net -21.2 vs -35.6.

So the rank channel is a **loss-mitigation ordering, not a winner selector**. The
protocol's research question is "which pre-earnings events become the big winners
that carry the strategy's P&L (top decile = 36% of |P&L|)". A rank-IC whose own
top decile holds none of the winners does not answer that question, and a
long-straddle book cannot monetise "loses 8.9% instead of 15.0%". The note's
NULL-WITH-POWER tail verdict is correct but understates the problem: it is not
only that the tail effect is below the detectable floor, it is that the winners
sit in the middle of the signal's distribution. Minor: the note calls the
detectable floor a "harness bootstrap SE"; in perm mode no bootstrap SE is
computed — it is a perm-z inversion. The direction of that error is conservative.

Also confirmed for the vol-level alternative: **X0085**, `im_entry/ratio_avg_rm`
tail = -0.00283, p=1.0, **sign fails the "+" prediction**. The vol-level factor
has no big-winner concentration either.

## 7. KV6 — trial-count honesty: the NOTE IS HONEST; the arithmetic is marginal

The note reports all 8 H11-tagged entries, including both skeptic probes and both
decomposition probes, and states that variants count. I found **no hidden or
abandoned H11 variants** — logged H11 entries are exactly {X0051, X0054, X0056,
X0060, X0062, X0066, X0068, X0069}, all 8 disclosed. Credit where due.

The wider accounting the note does not do:

- Pre-audit log = **74** entries; by hypothesis: H1 12, H12 10, H11 8, H7 7,
  H3 6, H2 5, H6 5, H5 4, H13 4, H14 4, H4 3, H9 3, H10 3.
- Probes touching the prior-move-history feature family (ratio_avg_im,
  ratio_last_im, ratio_avg_rm, ratio_last_rm, n_prior_im, n_prior_rm) =
  **35 entries / 29 distinct feature x target x p-mode combinations**.
- My replays plus 2 audit probes bring the log to **85**.

Bayes and multiplicity at the honest t=3.32 (not the floor-inverted 3.48):

- MBF = exp(-t^2/2) = **0.00405**; at a 1:9 prior, posterior odds = **27.5:1**
  (P(H1) about 0.965) — *for a single, pre-specified test*.
- At the full trial count N=74: expected max |t| of pure noise is
  sqrt(2 ln 74) = **2.93**. Observed 3.32 clears it by 0.4 t-units only.
- Bonferroni at N=74 on the honest two-sided p (0.00090) = **0.067, fails 0.05**.
  Using the floored p=0.0005 gives 0.037, but that number is not measurable at
  2000 permutations.
- Registry arithmetic (m=6, BH q=0.10, lone survivor needs p <= 0.0167): the ic
  leg would pass; the median leg (0.01599) sits right on the line; the tail leg
  fails outright.

So: not a hidden-trial scandal, but "p at the floor" overstates the evidence. At
the disclosed trial count the headline is **marginal, not decisive**.

## 8. KV7 — strongest alternative explanation: TRADING-COST / LIQUIDITY PROXY

This is the finding that most damages the mechanism claim.

- IC(avg_rm, long_ret_**net**) = **+0.2105**, but
  IC(avg_rm, long_ret_**gross**) = **+0.0914** (n=675).
  **Over half the effect disappears when costs are removed.**
- For the H11 ratio itself: net +0.1526 vs **gross +0.1068**; delta-hedged net
  +0.1515 vs delta-hedged gross +0.0903.
- Why: spearman(avg_rm, spread_frac_entry) = -0.223,
  spearman(avg_rm, spread_frac_exit) = -0.251, and
  **IC(spread_frac_exit, net) = -0.524**, IC(spread_frac_entry, net) = -0.456 —
  three times the size of anything H11 does. Names with big historical earnings
  moves have big-premium options and therefore a small *relative* bid-ask, so
  they bleed less round-trip cost. Partial IC(avg_rm, net | spread_frac_entry)
  falls to **+0.126**; partial IC(H11, net | spread_frac_entry) falls to +0.121.
- Smoking gun for the cost interpretation: across the panel,
  **spearman(long_ret_net, short_ret_net) = +0.46** (n=2356), and
  spearman(long_ret_gross, short_ret_gross) = +0.12. The *long and short legs of
  the same straddle rank together*. That is only possible if the net-return rank
  is dominated by a common friction term rather than by directional payoff. Any
  feature correlated with relative spread will therefore show a net-return IC.

A residual does survive: avg_rm predicts the realised payoff ratio
|realized_move|/im_entry at IC +0.131 (n=675), so the vol-level factor is not
*purely* friction. But roughly half the headline is trading cost, the registered
statistic is net return, and the frozen harness cannot separate the two.

Second alternative, unfalsifiable here: **regime.** The entire footprint is
2025H1. "High-realized-vol small caps outperformed in the first half of 2025" is
observationally equivalent to the H11 mechanism given zero coverage of 2024Q3/Q4.

## 9. What the promotable object is, and what it would need

Neither the H11 ratio nor ratio_avg_rm. The only object with any claim is the raw
level `im_entry/ratio_avg_rm` = **the name's average prior realized earnings
move** (X0084: IC +0.206, n=695), because both registered candidates are
near-monotone transforms of it and im_entry contributes nothing (IC -0.013).
Before any registry re-lock it would need, at minimum:

1. A **gross-return** and spread-controlled leg. If it does not survive on
   long_ret_gross it is a cost model, not a signal. Current evidence: it
   survives, at +0.09 rather than +0.21.
2. **Coverage outside 2025H1.** The nearest wide-coverage sibling with 2024
   presence is `ratio_last_rm` (n=1340, including 578 in 2024Q4) — a cross-regime
   version of the same idea should be tested there before anything is registered.
3. An honest **tail statement**: X0085 shows the vol-level factor has no
   big-winner concentration and its tail sign *fails* the prediction. If the
   deliverable is a top-decile selector, this family currently has nothing.
4. Multiplicity accounting at N >= 85 with the 29-combination feature family
   declared, not the 8-row H11 slice.

Registry re-lock is **not recommended** on this evidence. R1-R6 as locked are
unaffected by this audit.

## 10. Log entries created by this audit

Replays X0075-X0083; new alternative-statistic probes X0084
(`im_entry/ratio_avg_rm` ic perm, +0.20599, n=695, p=0.0005) and X0085 (same,
tail, -0.00283, p=1.0, sign fails). All count toward the trial total.
Ad-hoc stratification, jackknife and partial-correlation figures in sections 2-8
are **AUDIT-DIAGNOSTIC, read-only pandas, NOT promotable**; only the harness
entries above are official.
