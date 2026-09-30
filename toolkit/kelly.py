#!/usr/bin/env python
"""kelly.py -- Kelly criterion engine: portfolio Kelly diagnostics + bet sizing.

What it does
------------
1. `portfolio`  -- measures what Kelly multiple your CURRENT portfolio is
                   running at (equities and delta-adjusted derivatives).
                   Data via yfinance. Answers: "am I at 0.3x Kelly or 1.8x?"
2. `bet`        -- closed-form Kelly for a binary bet (win prob + odds).
3. `scenarios`  -- exact Kelly for one or many simultaneous bets given a
                   scenario-return matrix (CSV). Works for ANY payoff shape.
4. `straddle`   -- Kelly-sizes a long or short straddle: hold to expiry, or
                   hold over an event (earnings) with IV crush, using a
                   Monte Carlo / empirical-move scenario engine.

The math and derivations live in KELLY_RESEARCH.md next to this file.

Run (requires numpy/scipy/pandas/yfinance):
  python kelly.py ...

Examples
--------
# What Kelly is my portfolio running at?
python kelly.py portfolio --positions positions.csv --bankroll 250000

# Binary bet: 55% to double, else lose stake
python kelly.py bet --p 0.55 --win 1.0 --loss 1.0 --bankroll 100000

# Long 30d ATM straddle, market IV 25, you forecast realized 32
python kelly.py straddle --side long --hold expiry --spot 100 --strike 100 \
    --dte 30 --iv 0.25 --forecast-vol 0.32 --bankroll 100000

# Volatility-Vibes-style earnings vol sale: short the 7-DTE straddle at 85 IV,
# exit after the event at 45 IV, earnings move drawn from past moves file
python kelly.py straddle --side short --hold event --spot 950 --strike 950 \
    --dte 7 --iv 0.85 --iv-exit 0.45 --moves-file nvda_moves.csv \
    --bankroll 100000 --concurrent 4

# Arbitrary strategy payoffs (columns = bets, rows = scenarios, values =
# return per $1 committed to that bet)
python kelly.py scenarios --file scen.csv --bankroll 100000

positions.csv format for `portfolio`
------------------------------------
symbol,kind,qty,mult,delta,exp_return
AAPL,stock,200,,,
NVDA,stock,100,,,0.18
SPY,option,-10,100,0.45,

kind: stock | etf | option | cash (cash rows are ignored)
qty:  shares for stock, contracts for option (negative = short)
mult: option contract multiplier (default 100)
delta: option delta per share (required for option rows; puts are negative)
exp_return: optional expected annual TOTAL return override (decimal)
"""

from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

TRADING_DAYS = 252.0


# ---------------------------------------------------------------------------
# Core Kelly math
# ---------------------------------------------------------------------------

def kelly_binary(p: float, win: float, loss: float) -> float:
    """Closed-form Kelly for a binary bet.

    p: probability of winning. win: gain per $1 staked. loss: loss per $1
    staked. Maximizes p*ln(1+f*win) + (1-p)*ln(1-f*loss).
    """
    return p / loss - (1.0 - p) / win


def log_growth(f, r, probs=None) -> float:
    """Expected log growth per period E[ln(1 + f.r)]. NaN if infeasible."""
    r = np.asarray(r, float)
    if r.ndim == 2:
        w = 1.0 + r @ np.asarray(f, float)
    else:
        w = 1.0 + float(f) * r
    if np.any(w <= 0.0):
        return float("nan")
    p = np.full(w.shape[0], 1.0 / w.shape[0]) if probs is None else np.asarray(probs, float)
    return float(np.sum(p * np.log(w)))


def solve_kelly_1d(r, probs=None, cap=20.0):
    """Maximize E[ln(1+f*r)] over scalar f via bisection on the derivative.

    r: array of scenario returns per $1 committed. Returns (f_star, notes).
    The feasible domain keeps 1 + f*r > 0 for every scenario, so ruin in any
    scenario is priced at -infinity, exactly as Kelly intends.
    """
    r = np.asarray(r, float)
    p = np.full(r.shape[0], 1.0 / r.shape[0]) if probs is None else np.asarray(probs, float)
    notes = []
    pos = r[r > 1e-12]
    neg = r[r < -1e-12]
    lo = float(np.max(-1.0 / pos)) if pos.size else -cap
    hi = float(np.min(-1.0 / neg)) if neg.size else cap
    if not pos.size:
        notes.append("no winning scenarios: any long stake is -EV")
    if not neg.size:
        notes.append("no losing scenarios in the sample: Kelly is unbounded, capped at %.1f" % cap)
    lo = max(lo, -cap)
    hi = min(hi, cap)
    span = hi - lo
    a, b = lo + 1e-9 * span, hi - 1e-9 * span

    def dg(f):
        return float(np.sum(p * r / (1.0 + f * r)))

    da, db = dg(a), dg(b)
    if da <= 0.0:
        return a, notes + ["optimum pinned at lower bound"]
    if db >= 0.0:
        return b, notes
    for _ in range(200):
        m = 0.5 * (a + b)
        if dg(m) > 0.0:
            a = m
        else:
            b = m
    return 0.5 * (a + b), notes


def solve_kelly_nd(R, probs=None):
    """Maximize E[ln(1 + R @ f)] over vector f (k simultaneous bets).

    R: (n_scenarios, k) matrix of returns per $1 committed to each bet.
    """
    from scipy.optimize import minimize

    R = np.asarray(R, float)
    n, k = R.shape
    p = np.full(n, 1.0 / n) if probs is None else np.asarray(probs, float)

    def neg_g(f):
        w = 1.0 + R @ f
        if np.any(w <= 1e-12):
            return 1e12
        return -float(np.sum(p * np.log(w)))

    def jac(f):
        w = 1.0 + R @ f
        w = np.maximum(w, 1e-12)
        return -(p / w) @ R

    cons = [{"type": "ineq", "fun": lambda f: 1.0 + R @ f - 1e-9, "jac": lambda f: R}]
    res = minimize(neg_g, np.zeros(k), jac=jac, constraints=cons,
                   method="SLSQP", options={"maxiter": 1000, "ftol": 1e-12})
    return res.x


def kelly_gaussian(mu_ex, cov):
    """Unconstrained continuous-time Kelly weights: f* = Sigma^-1 (mu - rf)."""
    mu_ex = np.asarray(mu_ex, float)
    cov = np.asarray(cov, float)
    try:
        return np.linalg.solve(cov, mu_ex)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(cov) @ mu_ex


def growth_gaussian(w, mu_ex, cov, rf=0.0) -> float:
    """Long-run log growth of constant-weights portfolio (Gaussian approx)."""
    w = np.asarray(w, float)
    return float(rf + w @ mu_ex - 0.5 * w @ cov @ w)


def prob_ever_losing(x: float, kelly_multiple: float) -> float:
    """P(equity ever falls to fraction x of start) when running at a constant
    `kelly_multiple` of full Kelly (GBM approximation): x ** (2/m - 1)."""
    if kelly_multiple <= 0:
        return 0.0
    expo = 2.0 / kelly_multiple - 1.0
    if expo <= 0:
        return 1.0
    return float(x ** expo)


# ---------------------------------------------------------------------------
# Black-Scholes
# ---------------------------------------------------------------------------

def _ncdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def bs_price(S: float, K: float, T: float, r: float, sigma: float, cp: str) -> float:
    """Black-Scholes European option price. T in years, cp in {'c','p'}."""
    if T <= 0.0 or sigma <= 0.0:
        fwd = S * math.exp(r * T) if T > 0 else S
        intr = max(0.0, fwd - K) if cp == "c" else max(0.0, K - fwd)
        return intr * math.exp(-r * T) if T > 0 else intr
    sqt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sqt
    d2 = d1 - sqt
    if cp == "c":
        return S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)


def straddle_value(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0.0:
        return abs(S - K)
    return bs_price(S, K, T, r, sigma, "c") + bs_price(S, K, T, r, sigma, "p")


# ---------------------------------------------------------------------------
# Scenario generation for the straddle engine
# ---------------------------------------------------------------------------

def draw_standardized(n: int, t_df: float, rng) -> np.ndarray:
    """Unit-variance shocks: normal, or Student-t standardized to var 1."""
    if t_df and t_df > 2.0:
        z = rng.standard_t(t_df, size=n)
        return z / math.sqrt(t_df / (t_df - 2.0))
    return rng.standard_normal(n)


def draw_moves(n: int, args, rng) -> np.ndarray:
    """Simple percent moves for the underlying (event-style distribution)."""
    if args.moves_file:
        import pandas as pd
        df = pd.read_csv(args.moves_file)
        col = "move" if "move" in df.columns else df.columns[-1]
        moves = pd.to_numeric(df[col], errors="coerce").dropna().values.astype(float)
        if moves.size == 0:
            raise SystemExit("moves file %s has no numeric 'move' column" % args.moves_file)
        if args.symmetrize:
            moves = np.abs(moves)
            return rng.choice(moves, size=n, replace=True) * rng.choice([-1.0, 1.0], size=n)
        return rng.choice(moves, size=n, replace=True)
    if args.move_sigma:
        return args.move_sigma * draw_standardized(n, args.t_df, rng)
    return None


def straddle_scenario_returns(args, rng):
    """Returns (R, meta): R = per-$1-of-premium returns for ONE straddle."""
    S, K = args.spot, (args.strike if args.strike else args.spot)
    T = args.dte / 365.0
    entry = args.entry_price if args.entry_price else straddle_value(S, K, T, args.rf, args.iv)
    if entry <= 0:
        raise SystemExit("entry premium is zero; check inputs")

    moves = draw_moves(args.n, args, rng)
    if moves is not None:
        moves = np.maximum(moves, -0.98)  # a stock cannot lose more than 100%
    if args.hold == "expiry":
        if moves is not None:
            S_T = S * (1.0 + moves)
        else:
            if not args.forecast_vol:
                raise SystemExit("expiry mode needs --forecast-vol (or --moves-file/--move-sigma)")
            z = draw_standardized(args.n, args.t_df, rng)
            v = args.forecast_vol
            S_T = S * np.exp((args.drift - 0.5 * v * v) * T + v * math.sqrt(T) * z)
        exit_val = np.abs(S_T - K)
    else:  # hold over the event, exit right after at crushed IV
        if moves is None:
            raise SystemExit("event mode needs --moves-file or --move-sigma")
        if not args.iv_exit:
            raise SystemExit("event mode needs --iv-exit (post-crush IV estimate)")
        S_after = S * (1.0 + moves)
        T_rem = max(args.dte - args.event_gap, 0.0) / 365.0
        exit_val = np.array([straddle_value(s, K, T_rem, args.rf, args.iv_exit)
                             for s in S_after])

    side = 1.0 if args.side == "long" else -1.0
    R = side * (exit_val - entry) / entry
    meta = {
        "entry": entry,
        "implied_move": entry / S,
        "breakeven_lo": K - entry,
        "breakeven_hi": K + entry,
    }
    return R, meta


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def pct(x, digits=2):
    return ("%." + str(digits) + "f%%") % (100.0 * x)


def money(x):
    return "$%s" % format(int(round(x)), ",")


def report_bet_sizing(R, bankroll, unit_cost=None, unit_label="contract",
                      title="Kelly sizing", cap=20.0):
    """Shared report for any 1-D scenario return vector R (per $1 committed)."""
    R = np.asarray(R, float)
    f_star, notes = solve_kelly_1d(R, cap=cap)
    edge = float(np.mean(R))
    win = float(np.mean(R > 0))
    p5, p50, p95 = np.percentile(R, [5, 50, 95])
    worst = float(np.min(R))

    print("=" * 64)
    print(title)
    print("=" * 64)
    print("Edge per $1 committed : E[R] = %+.4f   win rate = %s" % (edge, pct(win, 1)))
    print("R percentiles         : p5 %+.3f | median %+.3f | p95 %+.3f | worst %+.3f"
          % (p5, p50, p95, worst))
    for note in notes:
        print("NOTE: %s" % note)
    if edge <= 0:
        print("-> No positive edge under your assumptions. Kelly stake = 0.")
        if f_star < -1e-4:
            print("   (Kelly actually wants the OTHER side: f* = %+.4f)" % f_star)
        return f_star

    rows = [("FULL Kelly", 1.0), ("Half Kelly  (recommended ceiling)", 0.5),
            ("Quarter Kelly (estimation-error safe)", 0.25)]
    print("-" * 64)
    for label, lam in rows:
        f = lam * f_star
        g = log_growth(f, R)
        line = "%-38s f = %6.2f%% of bankroll   g = %+.4f/trade" % (label, 100 * f, g)
        if bankroll:
            dollars = f * bankroll
            line += "   -> %s" % money(dollars)
            if unit_cost:
                n_units = int(dollars // unit_cost)
                line += "  (%d %ss)" % (n_units, unit_label)
                if n_units == 0:
                    line += " <- one contract exceeds this budget; skip or find a smaller underlying"
        print(line)
    if bankroll:
        f_half = 0.5 * f_star
        loss_10 = float(np.mean(f_half * R < -0.10))
        print("-" * 64)
        print("At half Kelly: P(single trade costs >10%% of bankroll) = %s" % pct(loss_10, 2))
        print("Worst sampled scenario at half Kelly: %s of bankroll" % pct(f_half * worst, 2))
    return f_star


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_bet(args):
    q = 1.0 - args.p
    f_star = kelly_binary(args.p, args.win, args.loss)
    print("Binary Kelly: p=%.3f win=%.2f loss=%.2f" % (args.p, args.win, args.loss))
    print("Edge = %+.4f per $1 staked" % (args.p * args.win - q * args.loss))
    if f_star <= 0:
        print("f* = %+.4f -> negative edge, do not bet (or take the other side)." % f_star)
        return
    for label, lam in [("FULL Kelly", 1.0), ("Half Kelly", 0.5), ("Quarter Kelly", 0.25)]:
        f = lam * f_star
        g = args.p * math.log1p(f * args.win) + q * math.log1p(-f * args.loss)
        line = "%-14s f = %6.2f%%   growth/bet = %+.5f" % (label, 100 * f, g)
        if args.bankroll:
            line += "   -> %s" % money(f * args.bankroll)
        print(line)


def cmd_scenarios(args):
    import pandas as pd
    df = pd.read_csv(args.file)
    prob = None
    if "prob" in df.columns:
        prob = df["prob"].values.astype(float)
        prob = prob / prob.sum()
        df = df.drop(columns=["prob"])
    R = df.values.astype(float)
    names = list(df.columns)
    if R.shape[1] == 1:
        report_bet_sizing(R[:, 0], args.bankroll,
                          title="Kelly sizing -- bet '%s' (%d scenarios)" % (names[0], R.shape[0]),
                          cap=args.cap)
        return
    f = solve_kelly_nd(R, prob)
    g = log_growth(f, R, prob)
    print("Joint Kelly over %d simultaneous bets (%d scenarios), growth=%+.5f:"
          % (R.shape[1], R.shape[0], g))
    for name, fi in zip(names, f):
        line = "  %-16s f* = %+7.2f%%" % (name, 100 * fi)
        if args.bankroll:
            line += "   half-Kelly -> %s" % money(0.5 * fi * args.bankroll)
        print(line)
    print("Total gross commitment at full Kelly: %.1f%% of bankroll"
          % (100 * float(np.sum(np.abs(f)))))


def load_positions(path):
    import pandas as pd
    pos = pd.read_csv(path)
    pos.columns = [c.strip().lower() for c in pos.columns]
    for col in ("symbol", "kind", "qty"):
        if col not in pos.columns:
            raise SystemExit("positions file needs columns: symbol, kind, qty (+ mult/delta/exp_return)")
    pos = pos[pos["kind"].str.lower() != "cash"].copy()
    pos["symbol"] = pos["symbol"].str.upper().str.strip()
    return pos


def cmd_portfolio(args):
    import pandas as pd
    import yfinance as yf

    pos = load_positions(args.positions)
    symbols = sorted(pos["symbol"].unique().tolist())
    bench = args.benchmark.upper()
    tickers = sorted(set(symbols) | {bench})

    print("Fetching %d tickers (%s of history)..." % (len(tickers), args.history))
    px = yf.download(tickers, period=args.history, auto_adjust=True, progress=False)["Close"]
    px = px.ffill().dropna()
    if px.empty or len(px) < 60:
        raise SystemExit("not enough price history downloaded; check tickers/connection")
    rets = np.log(px / px.shift(1)).dropna()
    spot = px.iloc[-1]

    # covariance (annualized), Ledoit-Wolf shrinkage when available
    r_assets = rets[symbols]
    cov_label = "sample"
    if not args.no_shrink:
        try:
            from sklearn.covariance import LedoitWolf
            lw = LedoitWolf().fit(r_assets.values)
            cov_d = lw.covariance_
            cov_label = "Ledoit-Wolf (shrink=%.2f)" % lw.shrinkage_
        except Exception:
            cov_d = r_assets.cov().values
    else:
        cov_d = r_assets.cov().values
    cov = cov_d * TRADING_DAYS

    # expected excess returns
    var_b = float(rets[bench].var())
    sig_b = math.sqrt(var_b * TRADING_DAYS)
    beta = np.array([float(rets[s].cov(rets[bench])) / var_b for s in symbols])
    if args.mu_source == "hist":
        mu_ex = r_assets.mean().values * TRADING_DAYS - args.rf
        mu_label = "historical mean (NOISY -- treat with suspicion)"
    else:
        mu_ex = beta * args.market_sharpe * sig_b
        mu_label = "CAPM prior (market Sharpe %.2f, bench vol %s)" % (args.market_sharpe, pct(sig_b, 1))
    # per-row overrides
    overrides = {}
    if "exp_return" in pos.columns:
        for _, row in pos.iterrows():
            v = row.get("exp_return")
            if pd.notna(v) and str(v).strip() != "":
                overrides[row["symbol"]] = float(v) - args.rf
    for i, s in enumerate(symbols):
        if s in overrides:
            mu_ex[i] = overrides[s]

    # delta-adjusted dollar exposure per symbol
    exposure = {s: 0.0 for s in symbols}
    for _, row in pos.iterrows():
        s = row["symbol"]
        kind = str(row["kind"]).lower()
        qty = float(row["qty"])
        if kind in ("stock", "etf"):
            exposure[s] += qty * float(spot[s])
        elif kind == "option":
            mult = float(row["mult"]) if pd.notna(row.get("mult")) else 100.0
            if not pd.notna(row.get("delta")):
                raise SystemExit("option row for %s needs a delta" % s)
            exposure[s] += qty * mult * float(row["delta"]) * float(spot[s])
        else:
            raise SystemExit("unknown kind '%s' (use stock/etf/option/cash)" % kind)

    expo = np.array([exposure[s] for s in symbols])
    w = expo / args.bankroll
    vol_i = np.sqrt(np.diag(cov))

    mu_p = float(w @ mu_ex)
    var_p = float(w @ cov @ w)
    sig_p = math.sqrt(max(var_p, 1e-18))
    sr_p = mu_p / sig_p if sig_p > 0 else 0.0

    f_star = kelly_gaussian(mu_ex, cov)
    sr_max = math.sqrt(max(float(mu_ex @ f_star), 0.0))

    print()
    print("=" * 72)
    print("PORTFOLIO KELLY REPORT")
    print("=" * 72)
    print("Bankroll %s | rf %s | mu: %s | cov: %s"
          % (money(args.bankroll), pct(args.rf, 1), mu_label, cov_label))
    print()
    print("%-8s %12s %8s %7s %9s %8s %12s" %
          ("symbol", "exposure", "weight", "beta", "mu_excess", "vol", "kelly w*"))
    for i, s in enumerate(symbols):
        print("%-8s %12s %7.1f%% %7.2f %9s %8s %11.1f%%" %
              (s, money(expo[i]), 100 * w[i], beta[i], pct(mu_ex[i], 1),
               pct(vol_i[i], 0), 100 * f_star[i]))
    print("-" * 72)
    print("Net exposure %s (%.2fx) | Gross %s (%.2fx)"
          % (money(expo.sum()), expo.sum() / args.bankroll,
             money(np.abs(expo).sum()), np.abs(expo).sum() / args.bankroll))
    print("Portfolio: mu_excess %s | vol %s | Sharpe %.2f"
          % (pct(mu_p, 2), pct(sig_p, 1), sr_p))

    out = {"weights": dict(zip(symbols, w.tolist())),
           "mu_excess": dict(zip(symbols, mu_ex.tolist())),
           "kelly_weights": dict(zip(symbols, f_star.tolist())),
           "portfolio": {"mu_excess": mu_p, "vol": sig_p, "sharpe": sr_p}}

    print()
    if mu_p <= 0:
        print("!! Your current direction has NON-POSITIVE expected excess return")
        print("   under these estimates. Kelly along this direction is zero (or")
        print("   the opposite sign). Fix the direction before worrying about size.")
        out["portfolio"]["kelly_multiple"] = None
    else:
        c_star = mu_p / var_p          # scale factor to reach full Kelly along ray
        lam = 1.0 / c_star             # the Kelly multiple you are running NOW
        g_now = args.rf + mu_p - 0.5 * var_p
        g_ray = args.rf + 0.5 * sr_p * sr_p
        g_max = args.rf + 0.5 * sr_max * sr_max
        print(">>> YOU ARE RUNNING AT %.2fx KELLY <<<" % lam)
        print("    (full Kelly along your current direction = %.2fx your current size)" % c_star)
        if lam > 1.0:
            print("    WARNING: you are OVER full Kelly. Growth is being destroyed by")
            print("    variance; above 2x Kelly long-run growth goes NEGATIVE.")
        elif lam > 0.5:
            print("    You are above half-Kelly -- aggressive given estimation error.")
        print()
        print("Long-run log growth (annualized, Gaussian approx):")
        print("  now: %s | full Kelly same direction: %s | unconstrained Kelly: %s"
              % (pct(g_now, 2), pct(g_ray, 2), pct(g_max, 2)))
        print("Direction efficiency: Sharpe %.2f vs best combination %.2f (%.0f%%)"
              % (sr_p, sr_max, 100 * sr_p / sr_max if sr_max > 0 else 0))
        print()
        print("Risk translation at your sizing (%.2fx Kelly), if held indefinitely:" % lam)
        for dd in (0.2, 0.5):
            print("  P(equity ever drops %s from here) ~ %s"
                  % (pct(dd, 0), pct(prob_ever_losing(1 - dd, lam), 1)))
        print()
        print("To move to HALF Kelly, multiply every position by %.2f" % (0.5 * c_star))
        print("To move to QUARTER Kelly, multiply every position by %.2f" % (0.25 * c_star))
        out["portfolio"].update({"kelly_multiple": lam, "scale_to_full_kelly": c_star,
                                 "growth_now": g_now, "growth_full_kelly_ray": g_ray,
                                 "growth_unconstrained": g_max})
    print()
    print("Caveats: option positions are DELTA-ADJUSTED only (gamma/vega ignored);")
    print("for a big options book, express it as scenarios and use `scenarios`.")
    print("Expected returns are the weakest input -- the report is only as good")
    print("as the mu column/prior you feed it.")
    if args.json:
        print()
        print(json.dumps(out, indent=2))


def cmd_straddle(args):
    rng = np.random.default_rng(args.seed)
    R, meta = straddle_scenario_returns(args, rng)

    K = args.strike if args.strike else args.spot
    title = ("Kelly sizing -- %s straddle, hold to %s | spot %.2f K %.2f, %g DTE"
             % (args.side.upper(), args.hold, args.spot, K, args.dte))
    print(title)
    print("Entry premium %.2f/share (%s per contract) | implied move +/-%s | breakevens %.2f / %.2f"
          % (meta["entry"], money(meta["entry"] * args.mult), pct(meta["implied_move"], 1),
             meta["breakeven_lo"], meta["breakeven_hi"]))
    if args.hold == "event":
        print("Exit: reprice at IV %s with %.1f days gone (IV crush %s -> %s)"
              % (pct(args.iv_exit, 0), args.event_gap, pct(args.iv, 0), pct(args.iv_exit, 0)))
    print()

    if args.concurrent > 1:
        # joint sizing of N independent simultaneous trades with equal stakes:
        # equivalent to 1-D Kelly on the sum of N independent scenario columns
        cols = [R]
        for _ in range(args.concurrent - 1):
            Ri, _ = straddle_scenario_returns(args, rng)
            cols.append(Ri)
        R_joint = np.sum(np.column_stack(cols), axis=1)
        f_joint, _ = solve_kelly_1d(R_joint)
        print("[%d concurrent independent trades like this one]" % args.concurrent)
        print("Joint Kelly: %.2f%% of bankroll EACH (%.2f%% total premium at risk)"
              % (100 * f_joint, 100 * f_joint * args.concurrent))
        f_solo, _ = solve_kelly_1d(R)
        if f_solo > 0:
            if f_joint < f_solo:
                note = "simultaneous bets compete for the same bankroll, so each shrinks"
            else:
                note = ("diversifying the tail across independent events allows a bit more "
                        "per trade -- ONLY if the moves are truly independent; if the events "
                        "share a market-wide shock, size each at f/N instead")
            print("(vs %.2f%% sized alone: %s)" % (100 * f_solo, note))
        print()

    unit_cost = meta["entry"] * args.mult
    report_bet_sizing(R, args.bankroll, unit_cost=unit_cost, unit_label="straddle",
                      title="Per-trade sizing (fraction = premium %s / bankroll)"
                      % ("paid" if args.side == "long" else "sold"))
    if args.side == "short":
        print()
        print("Short-premium notes: 'f' is premium sold / bankroll; losses can run to")
        print("several times premium, which the scenarios above price in ONLY as far")
        print("as your move distribution has tails. Use empirical moves or --t-df 3-5,")
        print("never a plain normal. Broker margin (~20% of notional) will likely bind")
        print("before Kelly does; the smaller of the two sizes wins.")


def build_parser():
    p = argparse.ArgumentParser(description="Kelly criterion engine -- see module docstring")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bet", help="closed-form binary-bet Kelly")
    b.add_argument("--p", type=float, required=True, help="win probability")
    b.add_argument("--win", type=float, default=1.0, help="gain per $1 staked (default 1)")
    b.add_argument("--loss", type=float, default=1.0, help="loss per $1 staked (default 1)")
    b.add_argument("--bankroll", type=float, default=None)
    b.set_defaults(func=cmd_bet)

    s = sub.add_parser("scenarios", help="Kelly from a scenario-return CSV")
    s.add_argument("--file", required=True,
                   help="CSV: one column per bet (return per $1), optional 'prob' column")
    s.add_argument("--bankroll", type=float, default=None)
    s.add_argument("--cap", type=float, default=20.0)
    s.set_defaults(func=cmd_scenarios)

    pf = sub.add_parser("portfolio", help="what Kelly multiple is my portfolio running at")
    pf.add_argument("--positions", required=True, help="positions CSV (see module docstring)")
    pf.add_argument("--bankroll", type=float, required=True, help="account equity in $")
    pf.add_argument("--rf", type=float, default=0.04, help="risk-free rate (default 0.04)")
    pf.add_argument("--history", default="3y", help="price history window (default 3y)")
    pf.add_argument("--mu-source", choices=["capm", "hist"], default="capm",
                    help="expected-return model when no exp_return override (default capm)")
    pf.add_argument("--market-sharpe", type=float, default=0.35,
                    help="assumed long-run market Sharpe for the CAPM prior")
    pf.add_argument("--benchmark", default="SPY")
    pf.add_argument("--no-shrink", action="store_true", help="disable Ledoit-Wolf shrinkage")
    pf.add_argument("--json", action="store_true", help="also print machine-readable JSON")
    pf.set_defaults(func=cmd_portfolio)

    st = sub.add_parser("straddle", help="Kelly-size a long/short straddle")
    st.add_argument("--side", choices=["long", "short"], required=True)
    st.add_argument("--hold", choices=["expiry", "event"], default="expiry",
                    help="hold to expiry, or exit right after an event with IV crush")
    st.add_argument("--spot", type=float, required=True)
    st.add_argument("--strike", type=float, default=None, help="default = spot (ATM)")
    st.add_argument("--dte", type=float, required=True, help="calendar days to expiry")
    st.add_argument("--iv", type=float, required=True, help="entry implied vol (annualized, e.g. 0.85)")
    st.add_argument("--entry-price", type=float, default=None,
                    help="override: actual straddle mid per share (else BS at --iv)")
    st.add_argument("--forecast-vol", type=float, default=None,
                    help="your realized-vol forecast for expiry mode (annualized)")
    st.add_argument("--iv-exit", type=float, default=None,
                    help="post-event IV estimate for event mode (e.g. RV30 or back-month IV)")
    st.add_argument("--event-gap", type=float, default=1.0,
                    help="days between entry and post-event exit (default 1)")
    st.add_argument("--moves-file", default=None,
                    help="CSV of historical event moves (column 'move', decimals)")
    st.add_argument("--move-sigma", type=float, default=None,
                    help="parametric event-move sigma (e.g. 0.06 = 6%%)")
    st.add_argument("--t-df", type=float, default=0.0,
                    help="Student-t degrees of freedom for shocks (0 = normal)")
    st.add_argument("--symmetrize", action="store_true",
                    help="bootstrap |moves| with random sign instead of raw moves")
    st.add_argument("--drift", type=float, default=0.0, help="annual drift for expiry mode")
    st.add_argument("--rf", type=float, default=0.04)
    st.add_argument("--n", type=int, default=100_000, help="Monte Carlo scenarios")
    st.add_argument("--bankroll", type=float, default=None)
    st.add_argument("--mult", type=float, default=100.0, help="contract multiplier")
    st.add_argument("--concurrent", type=int, default=1,
                    help="number of independent simultaneous trades like this one")
    st.add_argument("--seed", type=int, default=12345)
    st.set_defaults(func=cmd_straddle)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
