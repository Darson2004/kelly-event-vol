#!/usr/bin/env python
"""scripts/verify_vv_math.py -- numerical verification of the Volatility Vibes
pre-earnings long-straddle math (video 0YfQpYhMNH0).

Claims checked:
  A. Implied-move conversion: E|X| = sigma * sqrt(2/pi) for X ~ N(0, sigma^2).
  B. Variance additivity / event-vol extraction round-trips.
  C. "The IV ramp is mechanical": with constant event vol + constant ambient
     vol, quoted IV of the post-earnings expiry rises as DTE shrinks while the
     straddle (pin path) LOSES value.
  D. Martingale check: if ambient vol is fairly priced and event vol is NOT
     repriced, the unhedged T-14 -> T-0 long straddle has ~ZERO expected P&L
     (the event variance you bought is still in the exit price). So the whole
     edge = event repricing + (ambient realized - ambient implied) - costs.
  E. His repricing sim (implied move 4.2% -> 7.5%): expected P&L turns
     decisively positive; pin-path P&L alone is roughly flat.
  F. Break-even repricing vs round-trip cost, and the event share of premium.
"""
import math
import numpy as np

rng = np.random.default_rng(7)
C = math.sqrt(2.0 / math.pi)          # 0.79788
DAYS = 365.0

def straddle_bs(S, K, T, sigma, r=0.0):
    """Black-Scholes ATM-ish straddle, r=0 keeps the martingale check clean."""
    if T <= 0 or sigma <= 0:
        return abs(S - K)
    sqt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sqt
    d2 = d1 - sqt
    from math import erf
    N = lambda x: 0.5 * (1.0 + erf(x / math.sqrt(2.0)))
    call = S * N(d1) - K * N(d2)
    put = call - S + K
    return call + put

def total_iv(move, sig_a, dte):
    """Quoted IV of an expiry containing 1 event day + (dte-1) ambient days.
    move = implied earnings move (mean abs), sig_a = annualized ambient vol."""
    var_evt = (move / C) ** 2                # event-day variance (daily units)
    var_amb = sig_a ** 2 / DAYS              # ambient daily variance
    tot = var_evt + var_amb * (dte - 1)      # total variance to expiry
    return math.sqrt(tot / (dte / DAYS))     # annualize

print("=" * 72)
print("A. Implied-move constant")
x = rng.standard_normal(20_000_000) * 0.0627
print("   MC E|X|/sigma = %.5f   sqrt(2/pi) = %.5f" % (np.mean(np.abs(x)) / 0.0627, C))

print("=" * 72)
print("B. Event-vol extraction round-trip")
move_true, sig_a, dte = 0.05, 0.30, 14
iv_tot = total_iv(move_true, sig_a, dte)
# recover: sigma_evt^2 = iv_tot^2*(dte/365) - sig_a^2*(dte-1)/365
var_evt = iv_tot**2 * dte / DAYS - sig_a**2 * (dte - 1) / DAYS
move_rec = math.sqrt(var_evt) * C
print("   planted move 5.00%% -> quoted IV %.1f%% -> recovered move %.2f%%"
      % (100 * iv_tot, 100 * move_rec))

print("=" * 72)
print("C. Mechanical ramp (constant move 5%, ambient 30%): pin-path straddle")
print("   %-5s %-10s %-14s" % ("DTE", "quotedIV", "straddle/spot"))
for d in (20, 14, 10, 7, 5, 3, 2, 1):
    iv = total_iv(0.05, 0.30, d)
    st = straddle_bs(100, 100, d / DAYS, iv) / 100
    print("   %-5d %-10s %-14s" % (d, "%.1f%%" % (100 * iv), "%.2f%%" % (100 * st)))

print("=" * 72)
print("D. Martingale check: fair ambient, NO event repricing, unhedged")
print("   enter T-14 (expiry has event on day 14, exit T-0 = 1 DTE left)")
n = 2_000_000
S0, K = 100.0, 100.0
move, sig_a, d_in, d_out = 0.05, 0.30, 14, 1
iv_in = total_iv(move, sig_a, d_in)
entry = straddle_bs(S0, K, d_in / DAYS, iv_in)
# simulate 13 ambient days of GBM at sig_a (no event day inside the hold)
tau = (d_in - d_out) / DAYS
z = rng.standard_normal(n)
S_exit = S0 * np.exp(-0.5 * sig_a**2 * tau + sig_a * math.sqrt(tau) * z)
iv_out = total_iv(move, sig_a, d_out)          # same event vol at exit
vals = np.array([straddle_bs(s, K, d_out / DAYS, iv_out) for s in S_exit[:200_000]])
pnl = vals.mean() - entry
print("   entry %.4f | E[exit value] %.4f | E[P&L] %+.4f  (%+.2f%% of premium)"
      % (entry, vals.mean(), pnl, 100 * pnl / entry))
pin = straddle_bs(S0, K, d_out / DAYS, iv_out) - entry
print("   pin-path (no move) P&L: %+.2f%% of premium  <- his 'straddle bleeds' chart"
      % (100 * pin / entry))

print("=" * 72)
print("E. His repricing sim: implied move 4.2% -> 7.5% into the event")
move_in, move_out = 0.042, 0.075
iv_in = total_iv(move_in, sig_a, d_in)
entry = straddle_bs(S0, K, d_in / DAYS, iv_in)
iv_out = total_iv(move_out, sig_a, d_out)
vals = np.array([straddle_bs(s, K, d_out / DAYS, iv_out) for s in S_exit[:200_000]])
print("   E[P&L] = %+.2f%% of premium | pin-path P&L = %+.2f%%"
      % (100 * (vals.mean() - entry) / entry,
         100 * (straddle_bs(S0, K, d_out / DAYS, iv_out) - entry) / entry))

print("=" * 72)
print("F. Break-even repricing vs costs + event share of premium")
iv_in = total_iv(0.05, sig_a, d_in)
entry = straddle_bs(S0, K, d_in / DAYS, iv_in)
amb_only = straddle_bs(S0, K, d_in / DAYS, math.sqrt(sig_a**2 * (d_in - 1) / d_in))
print("   at T-14, move=5%%, ambient=30%%: event share of straddle premium = %.0f%%"
      % (100 * (entry - amb_only) / entry))
for cost in (0.01, 0.02, 0.03, 0.05):
    # find repricing (exit move) whose expected P&L covers the round-trip cost
    lo, hi = 0.05, 0.12
    for _ in range(40):
        m = 0.5 * (lo + hi)
        iv_out = total_iv(m, sig_a, d_out)
        ev = np.mean([straddle_bs(s, K, d_out / DAYS, iv_out)
                      for s in S_exit[:50_000]]) - entry
        if ev < cost * entry:
            lo = m
        else:
            hi = m
    print("   round-trip cost %2.0f%% of premium -> need exit move >= %.2f%% (repricing %+.0f%%)"
          % (100 * cost, 100 * m, 100 * (m / 0.05 - 1)))
