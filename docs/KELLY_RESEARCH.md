# The Kelly Criterion — research notes & toolkit

*Research + tooling built 2026-08-11. Companion scripts: `toolkit/kelly.py` (Kelly engine)
and `toolkit/vol_screen.py` (earnings-vol screen after the Volatility Vibes channel's
published filter).*

---

## 1. What Kelly actually is

Kelly (1956) answered: *if you can make a favorable bet repeatedly, what fraction
`f` of your bankroll should you stake each time?* The answer is the `f` that
maximizes the **expected logarithm of wealth** per bet:

```
f* = argmax_f  E[ ln(1 + f·R) ]        R = return per $1 committed
```

Why log, and not expected wealth? Because wealth compounds *multiplicatively*.
After `n` bets your wealth is `W_n = W_0 · Π (1 + f·R_i)`, so
`ln(W_n/W_0) = Σ ln(1 + f·R_i)` — an *additive* sum that the law of large numbers
applies to. Maximizing `E[ln(1+f·R)]` therefore maximizes the long-run compound
growth **rate** with probability 1. Breiman (1961) proved the strong properties:

- **G1**: the Kelly bettor's wealth eventually exceeds any other strategy's, a.s.
- **G2**: expected time to reach any large wealth target is asymptotically minimal.
- **B1 (the catch)**: full Kelly is violently volatile — at full Kelly the
  probability of at some point falling to a fraction `x` of your starting
  bankroll is exactly `x` (a 50% drawdown happens with probability 1/2!).

MacLean, Thorp & Ziemba's *"Good and Bad Properties of the Kelly Criterion"* is
the canonical summary: Kelly is the **growth-optimal ceiling**, not a comfort
target. Everything above it is strictly dominated; almost everyone should sit
below it.

Samuelson's critique, for completeness: log utility is *a* utility, not *the*
utility — Kelly is only "optimal" if you care about asymptotic growth. True, but
for a personal account being compounded for decades, asymptotic growth is a very
reasonable thing to care about, and the *ceiling* interpretation survives the
critique untouched: **no risk-preference justifies running above full Kelly.**

## 2. The formulas, from coin flips to portfolios

### Binary bet
Win probability `p`, gain `b` per $1, lose the stake:

```
f* = p − (1−p)/b            (even money: f* = 2p − 1 = "edge")
```

Asymmetric loss (lose `a` per $1 instead of all): `f* = p/a − (1−p)/b`.
`kelly.py bet` implements this. Sanity anchor: p=0.60 even money → f* = 20%.

### Arbitrary discrete/simulated outcomes
Maximize `Σ p_i ln(1 + f·r_i)` directly. The derivative `Σ p_i r_i/(1+f·r_i)`
is strictly decreasing, so bisection nails it (`solve_kelly_1d`). For `k`
simultaneous bets, maximize `E[ln(1 + R·f)]` over the vector `f`
(`solve_kelly_nd`, SLSQP). This scenario form is **exact for any payoff shape**
— it is the right tool for options.

### Continuous / Gaussian (the "leverage" form)
For an asset with annual excess return `μ−r` and variance `σ²`, continuously
rebalanced:

```
f* = (μ − r) / σ²                       (fraction of wealth, can exceed 1)
g(f) = r + f(μ−r) − ½ f²σ²              (long-run log growth)
g(f*) = r + ½·Sharpe²                   (max growth = half squared Sharpe)
```

Example: μ−r = 4%, σ = 16% → f* = 1.56× leverage. That number should already
feel scary — it is, see §4.

### Multi-asset (Thorp)
With excess-return vector `μ` and covariance `Σ`:

```
f* = Σ⁻¹ μ          g_max = r + ½ μᵀΣ⁻¹μ = r + ½·(max Sharpe)²
```

This is the tangency (max-Sharpe) portfolio levered to Kelly scale — Kelly and
Markowitz agree on *direction*; Kelly additionally fixes the *size*. In practice
`Σ⁻¹` is noise-amplifying, so `kelly.py portfolio` uses Ledoit-Wolf shrinkage by
default, and expected returns are the dominant error source (see §5).

### Discrete-period vs continuous-time — a trap we verified numerically
`f* = μ/σ²` assumes you rebalance continuously (wealth follows a GBM and never
gaps to zero). If instead you hold a **one-period** bet whose loss distribution
is wide (e.g. annual normal returns, μ=8%, σ=20%), exact one-period log-utility
gives a much smaller answer: our Monte Carlo run returned **f* ≈ 1.1, not the
closed-form 2.0** — the optimizer refuses sizes that can approach −100% in a
single period. At daily scale the same simulation converges to the closed form
(2.06 vs 2.00). Moral: **use the Gaussian formula for continuously-managed
portfolios; use scenario Kelly for discrete, chunky bets like options.**

## 3. What Kelly is my portfolio running at? (`kelly.py portfolio`)

The question decomposes into a **direction** and a **scale**. Let `w` be your
current weights (delta-adjusted exposure / bankroll). Along your own direction,
growth is `g(c) = r + c·wᵀμ − ½c²·wᵀΣw` for a scale factor `c`, maximized at:

```
c* = wᵀμ / wᵀΣw        →  full Kelly (your direction) = c*·w
λ  = 1/c*              →  the Kelly multiple you are RUNNING AT NOW
```

`λ = 0.5` means you sit at half Kelly; `λ = 1.8` means you are overbet and
burning growth; `λ ≥ 2` means your expected *growth* is negative even though
your expected *return* is positive — variance drag eats it.

The report also gives:
- **Direction efficiency**: your Sharpe vs the max-Sharpe combination `Σ⁻¹μ`
  (are you even pointed the right way?);
- **Growth now vs full-Kelly-same-direction vs unconstrained Kelly**;
- **Drawdown translation** (§4's formula) — the most intuitive risk number;
- The multiplier to move every position to half or quarter Kelly.

Derivatives enter as **delta-dollars** (contracts × mult × delta × spot). That
is honest for smallish moves but ignores gamma/vega — a big options book should
be expressed as scenario P&L and run through `kelly.py scenarios` instead.

**Positions file:**
```csv
symbol,kind,qty,mult,delta,exp_return
AAPL,stock,200,,,
SPY,option,-2,100,0.5,
```

**The μ problem.** Kelly output is only as good as expected returns, and
historical means are famously useless (3 years of data gives a standard error
of ~±9%/yr on a 16%-vol asset — bigger than the equity premium itself). Default
is a CAPM-style prior (`β × market Sharpe × market vol`, Sharpe 0.35); override
per-symbol via the `exp_return` column when you have a real view (e.g. from a
fundamental thesis). `--mu-source hist` exists but warns you.

## 4. Fractional Kelly — why everyone sane runs at 0.25–0.5×

Running at fraction `λ` of full Kelly (Gaussian world):

| λ (Kelly multiple) | growth captured `2λ−λ²` | P(ever −50%) `0.5^(2/λ−1)` | P(ever −20%) |
|---|---|---|---|
| 0.25 | 44% | 0.8% | 21% |
| 0.50 | 75% | 12.5% | 51% |
| 0.75 | 94% | 31% | 66% |
| **1.00 (full)** | **100%** | **50%** | **80%** |
| 1.50 | 75% | 71% | 90% |
| 2.00 | 0% | 100% | 100% |

Three structural reasons to be fractional:

1. **The asymmetry.** Underbetting by half costs 25% of growth; overbetting by
   half costs 25% *and* triples your drawdown probability; overbetting 2×
   zeroes growth entirely. When a parameter's error is punished asymmetrically,
   you shade toward the safe side.
2. **You don't know μ.** Kelly divides an *estimated* edge by an *estimated*
   variance. If your true edge is half what you think (usual), full Kelly on
   the estimate = 2× Kelly on the truth = zero growth. Half Kelly on a 2×
   overestimated edge still leaves you at full Kelly. Fractional Kelly is
   Bayesian shrinkage for overconfidence.
3. **Fat tails.** The Gaussian drawdown table above is the *optimistic* case;
   real returns gap. Scenario Kelly with Student-t or empirical tails
   (what `kelly.py straddle` does) already sizes smaller than Gaussian Kelly.

Equivalence worth knowing: fractional Kelly `λ` = the optimal policy for a CRRA
investor with risk aversion `γ = 1/λ` (Merton). Half Kelly ↔ γ=2, quarter ↔ γ=4.

## 5. Kelly for options — skewed payoffs need the scenario engine

Options break the Gaussian formulas: payoffs are convex/concave in the
underlying and the P&L distribution is deliberately skewed. The exact route is
the scenario form:

1. Simulate the underlying at your horizon **under your own forecast** (not the
   market's): lognormal with your vol forecast, Student-t for tails, or —
   best for events — a **bootstrap of actual past event moves**.
2. Reprice the structure in each scenario (intrinsic at expiry, or Black-Scholes
   at your post-event IV estimate for early exits).
3. `R = ±(exit − entry)/entry` per $1 of premium; maximize `E[ln(1+f·R)]`.

Normalization: `f` = **premium as a fraction of bankroll**.

- **Long premium** (long straddle): `R ≥ −1` always — worst case you lose the
  premium. Kelly can therefore justify surprisingly large `f` when the edge is
  real (a 35-vs-25 vol edge on a 30-DTE straddle sized to full Kelly ≈ 32% of
  bankroll in premium; run at quarter Kelly ≈ 8%).
- **Short premium** (short straddle): win rate is high (often ~90%) but losses
  run to many multiples of premium. In our reference run (85→45 IV crush, 6%
  moves, t₄ tails) the worst sampled scenario was **−18.8× premium**, and full
  Kelly came out at just **5.3%** of bankroll — the high win rate is almost
  irrelevant; the tail sets the size. This is why "sell vol, win 90% of the
  time" accounts blow up: they size off the win rate instead of the tail.
  Two hard rules: **never generate short-vol scenarios from a plain normal**,
  and remember broker margin (~20% notional) usually binds before Kelly.

**Multiple simultaneous events**: `--concurrent N` sizes N trades jointly (the
sum of independent scenario columns). Truly independent idiosyncratic events
let you hold slightly *more* per trade than solo Kelly (tail diversification);
correlated events (macro prints, same-sector earnings) must be sized at ~f/N.
The flag tells you which regime you're in.

## 6. The Volatility Vibes strategy through a Kelly lens

The referenced video — ["This Option Strategy Turned $10k Into $1 Million In One
Year"](https://www.youtube.com/watch?v=oW6MHjzxHpU) — is an **earnings
variance-risk-premium harvest**: markets systematically overprice near-term
earnings volatility, so sell the front-expiry ATM straddle (or the safer
calendar: short front / long back) right before the announcement and exit right
after the IV crush. The edge filter, popularized by the video and implemented in
[Acelogic's Earnings-Volatility-Calculator](https://github.com/Acelogic/Earnings-Volatility-Calculator),
is threefold:

| criterion | threshold | meaning |
|---|---|---|
| avg 30d share volume | ≥ 1,500,000 | options liquid enough to trade |
| IV30 / RV30 | ≥ 1.25 | implied rich vs **Yang-Zhang** realized vol |
| term-structure slope (front→45d) | ≤ −0.00406/day | event fear is concentrated in the front |

`vol_screen.py screen --ticker X` computes all three live (ATM IVs are backed
out of straddle mid prices by BS inversion — Yahoo's IV field is unreliable)
and prints the verdict plus a ready-to-run `kelly.py` sizing command.
`vol_screen.py moves --ticker X` exports the ticker's actual past post-earnings
moves as the empirical distribution for sizing.

What Kelly adds to the video's framework — the part sizing-by-feel gets wrong:

- **The strategy's whole risk is the tail.** Selling an implied move of ±6.5%
  against a name whose history contains a +24% earnings move is *negative* EV
  no matter the win rate — our NVDA test run returned exactly that verdict
  (E[R] = −0.24 per $1 of premium, Kelly = 0, "take the other side"). The screen
  finds candidates; **the empirical-move Kelly run is the veto**.
- When the trade *is* +EV, full Kelly lands in single-digit percent of bankroll
  per event; at the recommended 0.25–0.5× fraction that's roughly **1–3% of
  bankroll in premium per event** — which matches what disciplined vol sellers
  converge to by trial and error.
- The prior going in was that this edge is famous, crowded, and
  partially priced in. That doesn't make the pipeline useless — it makes the
  *veto* the valuable part, and the same machinery sizes any bet you actually
  do have an edge on (including fundamental long theses via
  `portfolio` + `exp_return` overrides).

**The full workflow:**
```bash
# 1. screen a candidate around its earnings date
python vol_screen.py screen --ticker CRWD
# 2. export its empirical earnings-move distribution
python vol_screen.py moves --ticker CRWD --out crwd_moves.csv
# 3. Kelly-size the short straddle (numbers from step 1's suggested command)
python kelly.py straddle --side short --hold event --spot 310 --strike 310 \
    --dte 4 --iv 0.95 --iv-exit 0.42 --entry-price 21.50 \
    --moves-file crwd_moves.csv --bankroll 100000 --concurrent 3
# 4. trade the SMALLER of: quarter-to-half Kelly, or margin capacity
```

## 6b. The buy-side mirror, tested on real data (2026-08 update)

The sell-side trade above has a mirror — the channel's later video: **buy** the
ATM straddle 1–2 weeks before earnings when the *implied earnings move* is
cheap versus the name's own history, exit just before the announcement, never
hold the print. Deep research + a full backtest harness live in
`event_bt/` (`RESEARCH.md` for the literature, `DATA_SPEC.md` for the
data). We ran it on real Databento OPRA NBBO quotes: 1,091 small/mid-cap
names, ~3,700 events, 2024-04 → 2026-01, fills at mid ± half the half-spread.

Three facts came out:

1. **The mispricing channel is real.** Cheap event vol gets repriced up into
   the announcement (slope t < −18; the effect survives conditioning only on
   realized-move history, which shares no quote noise with the signal), and
   the conditioned gross edge is ~+4% per trade, growing toward T-3 — matching
   the academic record (Gao-Xing-Zhang 2018).
2. **The spread is bigger than the edge.** These names quote straddles
   23–25% wide as a fraction of premium; the round trip costs ~3× the gross
   edge. Every executable configuration is deeply negative net.
3. **The Kelly veto now runs inside the backtest** (`kelly_f` in every stats
   block — same E[log(1+f·r)] machinery as `kelly.py`, f\*=0 means don't):

| configuration (T-7 entry) | mean/trade | Kelly f\* |
|---|---|---|
| unconditional long, net of spreads | −12.4% | **0.00 — VETO** |
| cheap-vs-implied-history rule, net | −11.6% | **0.00 — VETO** |
| cheap rule, *gross* (fantasy mid fills) | +3.6% | 1.01 |
| cheap-vs-realized-history rule, net | −8.0% | **0.00 — VETO** |
| short the crush (sell side!), net | −5.5% | **0.00 — VETO** |

*Note added at publication: the unconditional and short-leg rows above came from an
earlier pass of the engine. The published run summaries in
`results/smallcap_2024_2026/T7/summary.json` are authoritative. They give an
unconditional net of −17.3% and a short-leg net of −6.7%; the other rows match.*

The doctrine of §6 held in both directions: the screen finds the mispricing,
the empirical Kelly run vetoes the trade. Note the sell side ALSO vetoes in
this 2024–26 sample — the regime flipped to favor buyers (realized > implied),
which is precisely when the sell-side video's numbers stop working.

**The liquid-universe run (the decisive test, completed 2026-08-29):** same
harness, 42 liquid names (NVDA/AMD/TSLA/COST…), 971 events, **2020-09 →
2026-08**, median straddle spread 2.5% of premium. At T-14 entry, net of
half-spread fills and commissions:

| configuration (T-14, liquid, net) | mean/trade | n | t | Kelly f\* |
|---|---|---|---|---|
| cheap vs realized-move history | **+6.39%** | 193 | 2.7 | **0.81** |
| cheap vs implied-move history | +4.41% | 163 | 1.3 | 0.27 |
| short the crush on rich names | +5.55% | 227 | 1.3 | 0.12 |
| unconditional | +2.16% | 949 | 1.9 | 0.20 |
| VV's walk-forward linear model | +0.01% | 292 | 0.0 | **0.00 — VETO** |

The rm-rule cell is positive in 5 of 6 calendar years **including +11.8% in
2022** (a short-vol regime — kills the "it's just regime beta" objection),
symmetric across BMO/AMC sessions (leak check passed), and tail-driven
(median trade −4.9%; top decile = 36% of absolute P&L — the book must be wide
and patient). Ironies worth savoring: the *filter* works and the *fitted
model* the video actually sells is exactly zero OOS; and the same trade is
un-tradeable one liquidity tier down (small/mid caps: spreads eat 3× the
edge, all cells vetoed).

Disposition: **graduated to pilot** — quarter-Kelly ceiling but capped at
1–3% of bankroll in premium per name (concurrent earnings events are
correlated: size at f/N), mid-or-better patient limit orders only (the φ=0.5
fill assumption *is* the strategy), exit before the print, no exceptions,
paper-trade the first season to validate fills against the assumption.

## 7. Operating protocol

1. **Direction before size.** If `portfolio` says your Sharpe is a third of the
   achievable one, fixing weights beats fixing leverage.
2. **Size every new bet with scenarios**, empirical tails when available.
3. **Run the book at 0.25–0.5× Kelly.** Full Kelly is a ceiling, not a target.
4. **Recompute as bankroll moves** — Kelly is a fraction, so winning scales up
   and losing scales down automatically. Never "double down to get back".
5. **Cap the aggregate.** Individually-sized bets that share a factor are
   jointly overbet; when in doubt, size at f/N.
6. **Distrust your μ.** If halving your assumed edge flips the trade to
   negative growth, you have no trade.

## Sources

- J.L. Kelly Jr. (1956), *A New Interpretation of Information Rate* — [Bell System Technical Journal](https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf)
- E.O. Thorp (2006), *The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market* — [handbook chapter](http://www.eecs.harvard.edu/cs286r/courses/fall12/papers/Thorpe_KellyCriterion2007.pdf)
- MacLean, Thorp, Ziemba (2010), *Good and Bad Properties of the Kelly Criterion*
- [Kelly Criterion: Optimal Bet Sizing Explained — Quantt](https://www.quantt.co.uk/resources/kelly-criterion-explained)
- [Kelly's Criterion in Portfolio Optimization: A Decoupled Problem — arXiv:1710.00431](https://arxiv.org/pdf/1710.00431)
- [Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put-Writing on Index Options — arXiv:2508.16598](https://arxiv.org/html/2508.16598v1)
- [Exploring the Application of Kelly's Criterion in Portfolio Optimization — BSIC](https://bsic.it/exploring-the-application-of-kellys-criterion-in-portfolio-optimization/)
- [Volatility Vibes — "This Option Strategy Turned $10k Into $1 Million In One Year"](https://www.youtube.com/watch?v=oW6MHjzxHpU)
- [Acelogic/Earnings-Volatility-Calculator — the video's screen, open-sourced](https://github.com/Acelogic/Earnings-Volatility-Calculator)
- [Multivariable Kelly Criterion and Optimal Leverage Calculation from Data — SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5341539)
