# Volatility Vibes — full channel review (2026-08-12)

*Deep-dive on every video on the channel. Companion to `KELLY_RESEARCH.md` §6 (which
covers the short-earnings-straddle video) and `vol_screen.py`. Transcripts pulled and
analyzed 2026-08-12.*

## The channel

- **@VolatilityVibes** (channel id `UC0o3EucHQKZCUagsZt6TRAA`), created Nov 2024, ~49K subs,
  exactly **7 videos**. Bills himself as a "professional volatility trader… trying to correct
  misleading options educational content."
- Every strategy video funnels to **oquants.com** ("Option Quants") — his SaaS:
  $69–99/month for daily trade picks, vol/skew/momentum dashboards, 18y options data,
  250+ signals, backtester, Discord. The free videos give the recipe; the data the recipe
  needs (per-name implied/realized earnings-move history, ex-earnings IV, skew z-scores,
  FF screener) is the paid product. That is the correct lens for everything below.

## Video catalog

| # | Video | Date | Views | Type | Status |
|---|---|---|---|---|---|
| 1 | This Option Strategy Turned $10k Into $1M In One Year | Feb 2025 | 743K | **Strategy: short earnings straddle/calendar** | previously covered (KELLY_RESEARCH §6) |
| 2 | Black Scholes INTUITIVELY Explained | Feb 2025 | 51K | Education | reviewed |
| 3 | How to Trade Options Like a Quant | Apr 2025 | 124K | Process + VRP signals | reviewed |
| 4 | How to Spot 10x Vertical Spreads BEFORE They Take Off | Jul 2025 | 85K | **Strategy: skew-RV verticals + momentum** | reviewed |
| 5 | This Simple Options Strategy Crushes SPY (27% CAGR, 2.4 Sharpe) | Oct 2025 | 86K | **Strategy: Forward Factor calendars** | reviewed |
| 6 | The Earnings Volatility Strategy Big Funds Use | Dec 2025 | 27K | **Strategy: pre-earnings long straddle** | reviewed |
| 7 | The ONLY Options Trading Course You Need [3.5h Masterclass] | May 2026 | 98K | Education (course funnel, COURSE30 promo) | previously covered |

All four strategies are one family: **relative value on the vol surface** — event vol vs
its own history (#1, #6), front vs forward vol (#5), wing vs ATM skew (#4). No
"sell puts for income" nonsense anywhere; the math he shows (variance additivity,
forward vol, implied-move extraction) is correct — we verified his worked examples.

---

## Strategy 1 — Pre-earnings LONG straddle, exit before the announcement (video #6)

**Thesis.** Everyone knows IV ramps into earnings, but he (correctly) shows the ramp is
*mechanical*: as ambient days drop out of the expiry window, the fixed event variance is
packed into fewer days, so annualized IV must rise while total monetizable variance
*shrinks*. Unfiltered pre-earnings straddles ≈ break-even (his 21.5K-trade backtest:
mean +0.3%, median −6.3%, win rate 37%). The real bet: buy when the **event-vol
component (implied move) is cheap vs that name's own history** and it gets repriced up
into the event.

**Rules.** Long ATM straddle, nearest monthly expiry after earnings, enter T−14 (±4d),
exit just before the announcement (never hold the gap). Universe ≥20K avg daily option
volume. Four signals, all relative-value: implied move vs last implied, vs avg past
implied, vs last realized, vs avg past realized (all: lower ⇒ better). Linear regression,
expanding-window walk-forward from 2009, 2-year OOS blocks; trade predicted-return > 0.
Cap per trade at min($100K, 5% of daily option volume); size "2–6%"/small Kelly
(quotes Kelly ≈ 48.5% then disavows it).

**Claimed results (filtered, OOS).** Mean +3.3%, median **still −3.6%**, win rate ~42%,
"7-figure OOS equity curve" (no denominator, no Sharpe, no per-year breakdown).

**Holes.** Feature selection (which 4 signals survive; skew slope and raw implied move
dropped) was done on the *full sample* → the walk-forward is only partially OOS. Mean/median
gap means P&L lives in a small tail of winners (long-vol winners cluster in vol spikes —
the equity curve may be two episodes). Costs "applied" but never quantified — for 2-week
ATM single-name straddles exited on earnings day, round-trip spread is the whole ballgame.
Live coefficients = final refit on ALL data, never validated. The data the signals need is
exactly what oquants sells.

**Feasibility: the most credible of the new strategies, at half his claimed edge.**
The idea has real academic support (Gao–Xing–Zhang-style pre-earnings straddle results;
his "ramp is mechanical" point matches the literature). But +3.3% mean against 1.5–4%
realistic round-trip friction means the live edge is plausibly ~0–2% per trade, tail-driven,
with months-long drawdowns. **This is the mirror image of our existing screen**: `vol_screen.py`
sells rich event vol at T−0 (IV30/RV30 ≥ 1.25 + backwardation); this buys cheap event vol at
T−14 and exits into our entry point. The honest combined position: event vol is a
relative-value object — trade it both ways off the same per-name history. Pilot path:
invert the vol_screen inequalities (implied move *below* its own history), paper-trade with
real quoted spreads, and keep the empirical-move Kelly veto.

---

## Strategy 2 — "Forward Factor" calendars (video #5)

**Thesis.** Forward IV between two expiries systematically misprices future front IV.
FF = (front IV − forward IV)/forward IV, computed on **ex-earnings IV**. FF > 0 =
backwardation. Long calendar (sell front / buy back) ≈ long forward vol via variance
additivity. Credits a "Term Structure Forecast of Volatility and Options Portfolio Returns"
paper (the Vasquez 2017 JFQA line of results — real literature). Edge persistence story:
flow crowds the front, high-FF names are mid-cap-liquidity that vol funds skip.

**Rules.** ATM call calendar or ±35Δ double calendar; DTE pairs 30–60 / 30–90 / 60–90
(±5d); **enter when FF ≥ 0.20** (ex-earn or no earnings before back expiry); size 2–8%
(4% default), quarter Kelly; fill highest-FF first; close as a spread just before front
expiry; no adjustments.

**Claimed results.** 300K+ costed spread instances since 2007, ≥10K contracts/day filter.
Unconditional calendars: **negative mean** (his own baseline — honest). Filtered at tuned
thresholds (~20 trades/mo): mean +9–25%/trade, win rates 45–58%, portfolio backtests
17–28% CAGR, Sharpe 1.6–2.6 across an 18-cell grid. Headline "27% CAGR, 2.4 Sharpe" ≈ the
single best cell (double cal 60–90, fractional Kelly). Claims it grew his book "into the
mid-7 figures."

**Holes.** Break-even FF cutoffs (0.01–0.41, varying 40× across adjacent buckets — a noise
signature) read off **full-sample** decile plots, then re-tuned again to hit 20 trades/mo:
no OOS anywhere, and the entire edge lives inside the fitted threshold since the baseline
is negative. Slippage/commission values undisclosed — fatal for the instrument: his own live
example is a **$0.10-debit** AES calendar ($0.51/$0.61 legs) where 1¢/leg of slippage is
±20–40% of the position; exit modeled "just before close on expiry day," exactly when
markets are widest (his own losses exceed −100% of debit from round-trip costs). 300K
"observations" are overlapping and cluster in the same stress episodes → effective N far
smaller; per-trade Kelly (16–31%) ignores that simultaneous high-FF positions all lose
together when backwardation steepens. Live example (10/17 DTE) isn't even a tested pair.
Ex-earn IV history requires an ORATS-class dataset = his product.

**Feasibility: directionally real, numerically fantasy.** The term-structure premium is
documented and "never trade calendars blind, require genuine ex-earnings backwardation" is
sound hygiene — note it's the same backwardation condition our short-straddle screen uses
(slope ≤ −0.00406/day), monetized with defined risk instead of naked short vol. But the
quoted Sharpe will not survive real fills. If piloted at all: most-liquid names only
(penny-wide options), 60–90 DTE pairs (bigger debits, friction is a smaller fraction),
avoid-earnings variant (so plain IV works — no xearn needed), FF computable live with our
existing BS-inversion code, tiny size, treat as a live paper experiment since historical
validation needs paid chain history. Expect a fraction of claimed CAGR.

---

## Strategy 3 — Skew-mispriced verticals + momentum (video #4)

**Thesis.** Wing IV (10–25Δ) is inflated by hedging demand (puts) and lottery-chasing
(calls); the ATM is fairly supplied. A debit vertical = buy fair ATM, sell rich wing =
relative-value trade. Measure: 25Δ-vs-ATM skew z-score against the name's own history +
RV vs the specific leg IVs. Overlay time-series/cross-sectional/relative momentum; bull
verticals when momentum strong + call skew stretched. Hold 5–15 days, ride to near expiry,
exit before earnings absent an edge.

**Evidence shown.** No backtest. One Monte Carlo on an AMC spread (GBM at past RV: +23%
mean, **32% win rate**, edge $0.03 on a $0.17 debit) and **four hand-picked winners**
(QUBT +380%, SBET +280%, MP +400%, QS +160%) — all bull call spreads on melt-up meme names
(quantum/crypto-treasury/rare-earth/EV) during the May–Jul 2026 run.

**Holes.** By his own model the strategy loses ~⅔ of the time, yet the showcase is 4-for-4 —
pure survivorship, and momentum did the heavy lifting (his own drift table shows breakeven
at −50% annualized drift ⇒ P&L is drift-dominated; the "non-directional edge" framing
oversells). Circularity: he spends the intro explaining why lognormal Black-Scholes misses
fat tails, then computes the "edge" with a flat-vol lognormal Monte Carlo — in meme names
the 145–280% wing IVs may be *fair* compensation for exactly those jumps (SBET did an ATM
offering mid-run). Skew z-scores on stocks with weeks of history are noise. $0.03 theoretical
edge < the $0.05–0.10 bid-ask on the wing. Unmentioned: assignment/pin risk riding to expiry,
sizing for a 32%-hit-rate book, capped upside in names whose runs ARE the tail.

**Feasibility: not a strategy — a structuring habit.** As a systematic edge, unproven and
probably negative after frictions. As trade construction it's genuinely good practice: *when
you already want a directional bet in a high-skew lottery name, finance it by selling the
inflated wing rather than buying the call outright.* Adopt the construction, ignore the edge
claim. Relevant to entries on speculative names.

---

## Education videos (#2, #3, #7)

- **Quant-process video (#3)** is the best content on the channel. Real substance: VRP is an
  **index/ETF phenomenon, not single-name** (his AAPL counterexample: 2y of IV *under*
  realized); **short-vol loses precisely in the top two IV-percentile deciles** (contra
  Tastytrade "sell high IV rank"); butterfly > straddle for SPY VRP harvest (defined risk,
  smoother curve, ~35% max DD at 15% margin alloc); flat-forward/forward vol ratio as an
  underused signal (R²≈1%). His 5-step process (hypothesis → falsification → structure →
  fractional-Kelly size → "day-zero" management) is our own operating protocol in different
  clothes. Irony: after preaching test-set discipline he model-selects (linear vs logistic)
  on the test set. Showcase KWEB short straddle (Apr 2025, IV 68% vs RV 52%, exit at IV≈50%
  after the tariff vol crush) is honest-ish — he labels it "as good as it gets."
- **Black-Scholes intuition (#2)**: good retail pedagogy (N(d1)/N(d2) via discrete lognormal
  example), no strategy, minor conflations (N(d1) as exercise probability).
- **Masterclass (#7)**: 3.5h course consolidating all of the above; top-of-funnel for the
  COURSE30 oquants promo. Previously reviewed.

---

## Cross-channel verdict

1. **He is almost certainly a real vol trader, and the honest moments are unusually honest
   for YouTube**: "the IV ramp is not edge," "unconditional calendars lose," "median filtered
   trade still loses money," "VRP doesn't work in single names," full-Kelly disavowals.
   The math checks out everywhere we verified it.
2. **Every backtest fails the same way, always leaning flattering**: undisclosed costs,
   in-sample feature/threshold selection, headline = best grid cell, Kelly quoted for
   wow-factor, no per-year OOS breakdowns, unverifiable track-record claims ($6M+, mid-7
   figures). Trust the *sign* of his findings, never the *magnitude*. Working prior:
   live edge ≈ ⅓–½ of claimed, before asking whether your fills match his assumptions.
3. **The reproducibility gap is the business model.** Each strategy's binding constraint is
   a dataset (earnings implied/realized move history; xearn IV since 2007; skew z-score
   history) that is exactly the oquants subscription. The videos are high-quality lead
   magnets for a data/SaaS company — which also means the signals are being actively
   crowded by his own 49K subscribers, in the very mid-liquidity pocket he claims is the
   edge's moat.
4. **The channel arc is itself the lesson**: Feb 2025 = *sell* event vol at T−0; Dec 2025 =
   *buy* event vol at T−14 and exit into the seller's entry. Not a contradiction — a
   relative-value book. The tradeable object is the signal (event vol rich/cheap vs
   history), not the structure. Following either video without the conditioning signal is
   ~zero or negative EV **by his own data**.

## Built 2026-08-12: math verification + buy-side screen

- **`scripts/verify_vv_math.py`** — numerical verification of the pre-earnings long-straddle math.
  All his formulas check out (implied-move constant, variance additivity, mechanical
  ramp: IV 39.6%→119.7% while pin-path straddle falls 7.40%→5.00% of spot). Sharpening
  he never states: with fair ambient vol and no event repricing, the unhedged
  T−14→T−0 straddle is **exactly zero-EV before costs** (martingale — the event
  variance bought is still in the exit price; MC: +0.04%). So
  `EV = E[event repricing] + (ambient RV − ambient IV) − costs`. Break-even repricing:
  +3% of the implied move covers a 2% round-trip cost; +9% covers 5%. Event variance
  is only ~⅓ of straddle premium at T−14 (move 5%, ambient 30%).
- **`event_vol.py`** — buy-side screen (`screen --ticker X`) + `snapshot --tickers ...`
  which appends rows to `implied_move_history.csv`, accumulating the per-name
  implied-move history (the vs-past-implied signals) that free data can't backfill.
  First live run 2026-08-12 (10 names): cheap vs history = TGT 0.77, MRVL 0.84,
  SNOW 0.87 (ratio_last 0.34 — watch for T−14 entry ~Aug 19–26, earnings Sep 2);
  rich = HD 1.92, ADSK 1.63 (sell-screen candidates). "xearn" terminology in his
  videos ⇒ his data source is almost certainly ORATS.

## 2026-08-16: deep research + backtest harness built (Strategy 1)

Strategy 1 (pre-earnings long straddle) got a full deep-research pass and a
ready-to-run backtest harness: **`event_bt/`** (`bt.py` — selftest-verified
end-to-end on a synthetic world with planted properties). `RESEARCH.md` there
consolidates the literature/practitioner findings and pre-registers hypotheses
H1–H5; `DATA_SPEC.md` specifies the exact purchase (ORATS: $99 cores month for
the repricing-channel test, ~$698 total for full chains 2007+). Key research
deltas vs this doc: the only published pre-event long return lives at T-3→T-1
(not T-14 — earlier entry pays ~−2%/wk ambient premium); nobody anywhere has
replicated VV's numbers; the cheap-vs-history filter is documented mainly on
the short side; 2025-26 regime has flipped toward buyers (ORATS: realized >
implied for several seasons).

## What's worth doing with our stack

- Keep: `vol_screen.py` (sell-side screen) + empirical-move Kelly veto (KELLY_RESEARCH §6).
- Cheap extension: **buy-side event-vol screen** — same BS-inversion machinery, inverted
  thresholds (implied move below own history), T−14 entry / T−0 exit, paper-track with real
  quoted spreads. Start accumulating per-name implied-move history now (it's not
  backfillable for free).
- Optional small experiment: live FF calculation on liquid names (avoid-earnings variant,
  60–90 DTE); paper-trade only.
- Skew verticals: adopt as construction hygiene for directional bets in high-skew names;
  no systematic allocation.
- Do not subscribe for signals; the veto + sizing machinery we built is the durable part.
