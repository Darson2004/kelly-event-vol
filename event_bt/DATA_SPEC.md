# DATA_SPEC — what to buy / provide, and how to run (event_bt)

*Harness built + selftest-verified 2026-08-16. Companion: `RESEARCH.md` (why these
analyses), `VOLATILITY_VIBES_CHANNEL.md` (the source idea, video #6).*

The harness is **already runnable today**: `bt.py selftest` builds a synthetic
world with planted properties and proves the whole pipeline recovers them
(implied-move extraction ±2%, repricing slope, zero-EV unconditional, cost
drag, crush edge). When real data lands, it's three commands (see Runbook).

---

## The purchase decision (from the 2026-08-16 vendor research)

**ORATS is the recommended vendor — it is the only one that sells the signal
itself** (`impliedEarningsMove` per ticker-day, 2007+) plus full chains with
bid/ask, plus earnings dates with time-of-day, all from one internally
consistent ~15:46 ET snapshot.

| Tier | Cost | What it buys | What runs |
|---|---|---|---|
| **0 — free, running now** | $0 | `event_vol.py snapshot` keeps appending live implied moves to `implied_move_history.csv` | prospective signal history (not backfillable) |
| **1 — the thesis test** | **$99 (one ORATS Data API month, cancel)** | `hist/cores` (impliedEarningsMove daily, full history per ticker, 1 request each) + `hist/earnings` for ~100–300 names | `bt.py cores` — the repricing-channel analysis, the make-or-break question, 2007→present |
| **2 — the full backtest** | **~$698 one-time** ($99 API month + $599 ORATS bulk "Near EOD" SMV Strikes 2007→present via S3) | everything in Tier 1 + full chains with bid/ask every day | `bt.py ingest` → `validate` → `run` — all three analyses at real quoted spreads |
| 3 — fill realism (optional) | +$80/mo ThetaData Standard (2016+) | true 16:00 NBBO + tick quotes | cross-check ORATS 15:46 fills on the trade list |

Do **Tier 1 first**. If the repricing slope is ~0 in real data, the long-side
idea is dead and Tier 2 money is saved. If it's negative with a fat cheap-side
tail, Tier 2 tells you whether it survives spreads.

---

## Route B (CHOSEN 2026-08-16): Databento OPRA instead of ORATS

Built as `fetch_databento.py` (selftest-verified without network). Facts
verified 2026-08-16: OPRA.PILLAR **cbbo-1m** (last consolidated NBBO + last
sale per minute per contract) has history back to **2013-04-01**; usage-based
historical billing still exists alongside the $199/mo plan; an existing
Databento account (`DATABENTO_API_KEY`) was used.

Design (all encoded in the script):
- **One request per trading day**, all underlyings batched as parent symbols
  (`NVDA.OPT`), window **15:44–15:48 ET** (≈ ORATS' 15:46 snapshot
  convention; before the close, where a pre-event exit would actually trade).
  Earnings cluster on shared dates, so even 5,916 events = only ~467 requests.
- **`cost` prices the whole plan via metadata.get_cost before anything is
  billed** — run it, read the dollar number, then decide.
- Spot is not in the options feed: assembled as the **put-call-parity forward**
  (median of C_mid − P_mid + K over the 5 most-ATM strikes, nearest expiry) —
  internally consistent with the quotes and exactly the r=0 spot the engine
  assumes.
- Assembly filters: DTE 1–60, strikes ±30% of spot (do NOT narrow — the
  selftest proved narrow bands bias long-straddle results down), crossed
  quotes dropped, zero-bids kept.
- What Databento does NOT provide: implied moves (engine computes them — by
  design), and **earnings dates** (Route B still needs an events file).

### Events file for Route B

`prep-events` parses the existing Bloomberg export format directly
(`ticker,eventDate,callTime,earningsPeriod` with "ACT UW Equity"-style
tickers; BMO/AMC kept, intraday "DM" dropped). Current file on hand covers
**2024-05 → 2026-01, 1,201 small/mid-cap names, 5,916 usable events** — fine
for a first real run (and small-caps are where the literature says the effect
lives), but for the 2013+ deep backtest, re-export the same four columns from
Bloomberg for 2013-01-01 → present, ideally adding the liquid-options megacap
universe. Fallback if no terminal access: FMP earnings API (~$29/mo, session
flags need the validator's cross-checks).

### Route B runbook

```bash
PY=python
cd event_bt
export DATABENTO_API_KEY=...          # or pass --key

$PY fetch_databento.py prep-events --raw path/to/earnings.csv   # done 2026-08-16
$PY fetch_databento.py plan  [--tickers A,B,C]                # done (pilot+full)
$PY fetch_databento.py cost --plan data/db_plan_pilot.json    # price BEFORE buying
$PY fetch_databento.py fetch --plan data/db_plan_pilot.json --limit 5   # smoke
$PY fetch_databento.py fetch --plan data/db_plan_pilot.json   # resumable
$PY fetch_databento.py assemble                               # -> chains.csv
$PY bt.py validate && $PY bt.py run --entry-target 14,7,3
```

Plans already on disk: `data/db_plan_pilot.json` (10 names, 64 events, 324
request-days) and `data/db_plan_full.json` (5,916 events, 467 request-days).

### Exact ORATS pulls

API base `https://api.orats.io/datav2`, param `token=...`, append `.csv` for CSV.
≤10 tickers per request, 20k requests/month on the $99 tier.

Tier 1 (a few hundred requests total):
```
GET /hist/earnings.csv?ticker=AAPL
    -> ticker, earnDate, anncTod            (anncTod "0800"=BMO, "1630"=AMC)
GET /hist/cores.csv?ticker=AAPL&fields=ticker,tradeDate,impliedEarningsMove,exErnIv30d,iv30d,ernDate1,ernMv1
    -> full daily history in one paginated request per ticker
```
Concatenate the cores pulls into one CSV, the earnings pulls into another. Done.

Tier 2 bulk file (S3, one gzip zip per trading day, `ORATS_SMV_Strikes_YYYYMMDD.zip`),
verified header:
```
ticker,stkPx,expirDate,yte,strike,cVolu,cOi,pVolu,pOi,cBidPx,cValue,cAskPx,
pBidPx,pValue,pAskPx,cBidIv,cMidIv,cAskIv,smoothSmvVol,pBidIv,pMidIv,pAskIv,
iRate,divRate,residualRateData,delta,gamma,theta,vega,rho,phi,driftlessTheta,
extVol,extCTheo,extPTheo,spot_px,trade_date
```
The ingest adapter already maps these names (`cBidPx`→`call_bid`, `stkPx`→`spot`,
`trade_date`→`obs_date`, `cMidIv`/`pMidIv`→IV columns, …). Free sample to test
against right now: `https://s3.amazonaws.com/assets.orats.com/ORATS_SMV_Strikes_20240103.zip`.

---

## Canonical schema (what any vendor's data becomes)

Drop into `data/canonical/` (or let `bt.py ingest` build them):

**events.csv** — one row per earnings event
```
ticker,ann_date,session        # session: BMO | AMC | UNK (UNK treated as AMC)
```

**chains.csv** — one row per (obs day, ticker, expiry, strike)
```
obs_date,ticker,expiry,spot,strike,call_bid,call_ask,put_bid,put_ask[,call_iv,put_iv]
```
Coverage needed per event: daily rows from **T-20 to T+2**, expiries out to
~50 DTE (must include the first post-earnings expiry and, ideally, the last
pre-earnings expiry), strikes within **±20% of spot minimum — wider is better**
(narrow bands silently drop the big-move winners and bias the long side down;
the selftest reproduced exactly this bias at ±10%).

**cores.csv** (Tier 1 alternative — no chains)
```
tradeDate,ticker,impliedEarningsMove       # column names flexible
```

Non-ORATS vendors: `bt.py ingest --vendor generic --map map.json` where
map.json = `{"obs_date": "<your col>", "ticker": ..., ...}`.

---

## Runbook (when the data arrives)

```bash
PY=python
cd event_bt

# Tier 1 (cores + earnings only):
$PY bt.py cores --cores raw/orats_cores.csv --events-file raw/orats_earnings.csv

# Tier 2 (full chains):
$PY bt.py ingest --raw "raw/strikes/*.csv" --events-file raw/orats_earnings.csv
$PY bt.py validate                      # coverage + skip-reason report first
$PY bt.py run --entry-target 14,7,3     # all analyses + entry-timing sweep
$PY bt.py run --phi 1.0                 # stress: pay the full quoted spread
```

Outputs land in `results/`: `trades.csv`, `summary.json`,
`repricing_by_cheapness.csv`, `repricing_by_year.csv`, `replicate_trades.csv`,
`replicate_wf_by_year.csv`, `rvbook_trades.csv`, `rvbook_equity.csv`,
`repricing_scatter.png`.

## What the run reports

1. **Repricing channel** — slope/t of implied-move change (entry→T-0) on entry
   cheapness vs own history, quintile table, per-year stability. This is the
   entire long-side thesis in one number.
2. **Replicate VV #6 honestly** — unconditional baseline, fixed cheapness rule,
   expanding walk-forward OLS (fits only on trades already exited; 2-year OOS
   blocks), all gross AND net at real quoted spreads (`--phi`), unhedged and
   delta-hedged, with per-year OOS breakdown and a top-decile-share tail metric.
3. **RV book** — long cheap event vol T-14→T-0 + short rich event vol T-0→T+1
   (the crush), combined equity curve, CAGR / maxDD / Sharpe-like at `f` per trade.

## Data-quality gotchas (encoded or checked by `validate`)

- **Earnings date/session errors are the #1 killer** — a BMO tagged AMC makes
  the "pre-event exit" happen post-crush. Cross-check `anncTod` against the
  implied-move collapse day and the max |overnight gap|; drop UNK-session
  events pre-2010 rather than guessing.
- ORATS quotes are a **15:46 ET snapshot**, not the close — fine (pre-event
  exits should happen before the close anyway), but never mix another vendor's
  16:00 spot into the same P&L leg.
- Zero-bid legs corrupt straddle mids — the quote loader drops crossed/absurd
  quotes; keep an eye on `spread_frac_entry` medians in `trades.csv`.
- Weeklies barely existed before ~2011-2013 — the term-structure implied move
  from monthlies is biased low; prefer ORATS' solved `impliedEarningsMove` for
  the signal history pre-2013.
- Build the universe point-in-time (top-N by option volume per year), keep
  delisted names; the bulk files include them.
