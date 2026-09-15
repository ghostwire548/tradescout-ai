# TradeScout AI

A B2B intelligent lead-generation workbench for foreign-trade business.
Users create **Campaigns**, import or fetch prospective companies, the system
analyses company websites, scores leads, generates outreach copy, and saves
results to a local CRM + Excel.

> **Status: v0.7.0** — LLM integration (opt-in), real website analysis,
> multi-campaign management, CSV Lead import, and outreach message generation
> are implemented. Without an API key the app runs fully offline.
> See "Not implemented" below.

## Features

### Milestone 0
- Python 3.11 + Streamlit UI
- SQLite database via **SQLModel**
- Configuration via **Pydantic Settings** (`.env`, prefixed `TRADESCOUT_`)
- Base models: `Campaign`, `Lead`, `Message`
- **Mock mode** — 5 realistic leads + 1 demo campaign, no API key needed
- Edit a lead's CRM status in the UI and persist it to SQLite
- Export all leads to `.xlsx` (openpyxl)
- `pytest` tests for models and database

### Website analysis — real HTTP fetch + heuristic parser
- **Real HTTP fetching** via `requests` (10 s timeout, desktop User-Agent,
  auto `https://` prepend, redirect-following). No API key needed.
- **Heuristic HTML analysis**: extracts page `<title>`, `<meta name="description">`,
  detects known tech stacks from page source (Shopify, WordPress, WooCommerce,
  Wix, Squarespace, Magento, Google Analytics, Cloudflare, React, Vue.js,
  jQuery, Bootstrap, Tailwind CSS), and computes a signal score 0–40.
- Fetch errors are gracefully recorded as `ERROR` status with a descriptive
  message shown in the UI — the app never crashes on a failed fetch.
- The `fetcher` / `analyzer` interfaces remain swappable so an LLM-backed
  analyzer can be injected later without changing any caller.

### Lead scoring
- **Lead scoring framework** (`scoring.py`): swappable `ACTIVE_SCORER`
  (default deterministic heuristic, 0-100) plus `ScoreResult` with factor
  breakdown (website presence, email, industry, country tier, analysis signal).
- Country scoring is case-insensitive after v0.6.0 review fix.
- UI: bulk "分析全部官网" / "重新评分" actions, per-lead analysis + auto-score.

### LLM integration (opt-in, API key required)
- **Shared LLM client** (`llm.py`): OpenAI-compatible API via the `openai` library.
  Zero configuration needed — if `TRADESCOUT_LLM_API_KEY` is not set, all
  three modules gracefully fall back to their offline heuristics.
- **LLM message generation** (`messaging.py`): `llm_generator` builds
  personalized B2B outreach copy from lead data + analysis results. Falls back
  to the offline template engine when no key is configured.
- **LLM lead scoring** (`scoring.py`): `llm_scorer` blends heuristic baseline
  scores with an LLM-generated qualitative signal (0-40). Falls back to
  `default_scorer` without a key.
- **LLM website analysis** (`analysis.py`): `_llm_analyzer` extracts a
  human-readable company summary and signal score from scraped HTML. Falls
  back to the regex-based heuristic analyzer.
- **Auto-selection**: all three `ACTIVE_*` selectors pick LLM at import time
  when the key is present; restart the app after adding your key.

### CSV Lead import (data-ingest milestone)
- Upload a CSV, **map** source columns to `company_name / website / phone /
  email / address / country / city / category` (auto-suggested from headers;
  Chinese + English aliases; GBK/UTF-8 auto-detect).
- **Normalizes** company name, website → domain, phone, email on import.
- **Deduplicates**: prefer website domain; fall back to company name + phone.
- **Preview before import**: shows 新增 / 重复 / 无效 counts + a per-row table.
- **Commits** only the *new* rows inside one transaction, so a failed import
  never corrupts existing data. New `Lead` columns `phone / address / city`
  were added; `init_db` runs an additive ALTER migration that preserves data.
- `pytest` coverage for normalization, mapping, dedup and commit.

### Outreach message generation (Milestone: messages)
- **Message framework** (`messaging.py`): `generate_message()` delegates to a
  swappable `ACTIVE_GENERATOR`. The default is an **offline template engine**
  (no API key, no network) that composes B2B outreach copy from local Lead
  fields (+ optional prior website analysis).
- A reserved `llm_generator` interface is included; swap it in via
  `messaging.ACTIVE_GENERATOR = messaging.llm_generator` once an LLM backend
  is configured.
- UI: bulk "为全部线索生成话术" action, plus a per-lead "💬 开发话术" expander
  with channel select (email / linkedin / whatsapp), generate, editable preview,
  and save to the `Message` table. Messages are **generated and saved only** —
  the app never sends email.
- `pytest` coverage for the template generator, channel variants, the reserved
  LLM interface, generator swapping, and message persistence.

### Multi-campaign management
- **Interactive campaign selector** — switch between campaigns at the top of
  the Leads section; leads, bulk actions and messaging are all scoped to the
  active campaign.
- **Create campaigns** — "➕ 新建 Campaign" button opens an inline form (name +
  optional description).
- **CSV import** now includes a **target campaign picker** so imported leads
  land in the right campaign directly (falls back to the default campaign if
  no picker value).
- `pytest` coverage for campaign CRUD, lead filtering per campaign, and
  campaign-scoped CSV import.

## Project structure

```
tradescout-ai/
├── app.py                 # Streamlit entrypoint (campaigns + leads + import + messages)
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── src/
│   └── tradescout/
│       ├── __init__.py
│       ├── config.py      # Pydantic settings
│       ├── models.py      # SQLModel: Campaign / Lead / Message / WebsiteAnalysis
│       ├── db.py          # engine + session helpers (+ additive migration)
│       ├── mock_data.py   # 5 mock leads + demo campaign
│       ├── crm.py         # read leads, update CRM status + score, default campaign, messages
│       ├── analysis.py    # website analysis framework (reserved interfaces)
│       ├── scoring.py     # lead scoring framework (swappable scorer)
│       ├── importer.py    # CSV import: parse, map, normalize, dedup, commit
│       ├── messaging.py   # outreach message generation framework (reserved LLM interface)
│       └── export.py      # xlsx export (incl. analysis column)
└── tests/
    ├── test_models.py
    ├── test_database.py
    ├── test_analysis_scoring.py
    ├── test_importer.py
    ├── test_messaging.py
    └── test_campaign.py
```

## Setup & run (Windows)

```powershell
# 1. Create a virtual environment with Python 3.11
python -m venv .venv

# 2. Activate it
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the app
streamlit run app.py
```

Then open the printed `http://localhost:8501` URL. On first launch the app
seeds a demo campaign and 5 mock leads automatically.

## Run the tests

```powershell
.venv\Scripts\activate
python -m pytest
```

## Configuration

Copy `.env.example` to `.env` and adjust. Available keys (all prefixed
`TRADESCOUT_`):

| Key | Default | Description |
|-----|---------|-------------|
| `TRADESCOUT_APP_NAME` | `TradeScout AI` | App display name |
| `TRADESCOUT_DATABASE_URL` | `sqlite:///./tradescout.db` | SQLite database URL |
| `TRADESCOUT_MOCK_MODE` | `true` | Use built-in mock data |
| `TRADESCOUT_DEFAULT_CAMPAIGN_NAME` | `Demo Campaign` | Demo campaign name |
| `TRADESCOUT_LLM_API_KEY` | _(empty)_ | OpenAI-compatible API key |
| `TRADESCOUT_LLM_BASE_URL` | `https://api.openai.com/v1` | LLM API endpoint |
| `TRADESCOUT_LLM_MODEL` | `gpt-4o-mini` | Model name |

## Not implemented (future milestones)

- Real **API-based** company data fetching (e.g. Google Places) — CSV file
  import is the supported path.
- Authentication, multi-user support.
- Advanced bot-protection bypass (Playwright / headless browser fetching).

## Known issues / limitations

- Still local-only; the database is a single SQLite file.
- Website analysis uses real HTTP fetching (10 s timeout, desktop User-Agent).
  Sites behind Cloudflare/bot-protection may return empty or error pages.
- LLM features require `TRADESCOUT_LLM_API_KEY` in `.env`; without it the app
  runs fully offline with heuristic fallbacks that are always available.
- CSV import **invalid** = a row whose company name is empty after normalization
  (the `Lead.company_name` column is NOT NULL). Such rows are skipped.
- Dedup priority: website domain first; company name + phone as fallback. Within
  a single import batch, later rows matching an earlier new row are "duplicate".
- `init_db` runs an additive ALTER migration for `phone/address/city`; it never
  drops existing columns or rows.
- Mock data is seeded once; clearing the DB is required to re-seed.
- Outreach messages are **generated and saved only** — the app never sends
  email/SMS (per the no-auto-send constraint). Use the text preview to copy
  content into your own mailer.
- No pagination/large-dataset handling yet (fine for current volumes).
- Export currently exports **all** leads across all campaigns; JSON-export or
  per-campaign filtering for export is a possible next step.
- Designed and verified on Windows; paths use OS-agnostic separators.
- TRADE SCOUT AI — PROFITABILITY RESEARCH / EDGE VALIDATION MODULE

FIRST: INSPECT THE EXISTING TRADESCOUT AI CODEBASE

Before writing code:

1. Inspect the entire existing TradeScout AI repository.
2. Understand the current architecture, database schema, authentication, OANDA integration, technical-analysis engine, strategy engine, risk engine, trade journal, UI/navigation, tests, and Supabase Edge Functions.
3. Integrate this module into the EXISTING TradeScout AI architecture.
4. Do NOT create:
   - a disconnected demo
   - a mock dashboard
   - a duplicate application
   - fake backtesting
   - fake market data
   - fabricated performance results
   - hardcoded profitability numbers
5. Reuse existing:
   - OANDA integration
   - Supabase database
   - authentication
   - technical-analysis engine
   - risk engine
   - strategy engine
   - trade journal
   - market-data infrastructure
   - UI/navigation
   - existing testing infrastructure
6. If required functionality does not exist, implement it properly.
7. Preserve existing working functionality unless a change is required for this module.
8. Do not expose OANDA credentials in frontend code, URLs, logs, client-side environment variables, or UI.
9. OANDA LIVE remains the only execution environment. Do not reintroduce Practice execution.
10. Backtesting/research must remain completely separate from live execution.
11. A backtest must NEVER place a real OANDA order.
12. A research result must NEVER automatically enable live trading.
13. User approval remains mandatory before any live order.
14. Risk controls always have priority over signal generation.

IMPORTANT RESEARCH PRINCIPLE:

The purpose of this module is NOT to guarantee profits.

The purpose is to determine whether a strategy has statistically credible positive expectancy after realistic trading costs and whether that edge survives unseen data.

Backtesting provides evidence, not certainty.

Never claim:
- guaranteed profit
- guaranteed win
- future profitability
- 100% accuracy
- risk-free trading

When evidence is insufficient, the system must say:

NOT ENOUGH EVIDENCE

==================================================
1. STRATEGY RESEARCH LAB
==================================================

Create a Strategy Research Lab where strategies can be created, versioned, tested, compared, and retired.

Every strategy must have:

- unique strategy ID
- strategy name
- strategy version
- entry rules
- exit rules
- timeframe
- instruments
- market regimes
- risk configuration
- news rules
- parameter configuration
- creation date
- test dataset
- status

Statuses:

RESEARCH
BACKTESTING
OUT_OF_SAMPLE
WALK_FORWARD
OBSERVATION
VALIDATED
REJECTED
RETIRED

Never silently modify a strategy after testing.

Every parameter change creates a new strategy version.

Strategy versions must be immutable after testing.

==================================================
2. REALISTIC BACKTEST ENGINE
==================================================

Build a proper historical backtesting engine.

Historical decisions may ONLY use information available at that exact historical timestamp.

Prevent:

- look-ahead bias
- future candle leakage
- future news leakage
- future economic-calendar leakage
- future fundamental-data leakage
- survivorship bias where applicable

Use chronological processing.

Never allow future information to influence an earlier decision.

Create automated tests specifically proving chronological integrity.

==================================================
3. TRADING COST MODEL
==================================================

Backtests must account for realistic execution costs.

Include:

- bid/ask spread
- estimated slippage
- commissions where applicable
- financing/swap where applicable
- spread expansion
- news-period execution conditions

Allow configurable assumptions.

Run sensitivity tests using:

NORMAL COST

HIGH COST

EXTREME COST

A strategy that only works with unrealistically low costs must be flagged.

The after-cost result is the primary result.

==================================================
4. CORE PERFORMANCE METRICS
==================================================

Calculate:

- total trades
- winning trades
- losing trades
- win rate
- average win
- average loss
- largest win
- largest loss
- expectancy per trade
- expectancy in R
- profit factor
- maximum drawdown
- average drawdown
- maximum consecutive losses
- average holding time
- median holding time
- total return
- annualized return where appropriate
- risk-adjusted return
- Sharpe ratio where statistically appropriate
- Sortino ratio where statistically appropriate

Do not display metrics as statistically meaningful when the sample size is insufficient.

Clearly display sample-size warnings.

==================================================
5. R-MULTIPLE ANALYSIS
==================================================

Record every trade as R.

Example:

WIN +2.1R
LOSS -1R
WIN +1.4R

Calculate:

- average R
- median R
- R distribution
- positive expectancy
- largest negative R
- consecutive negative R

Display an R-distribution chart.

==================================================
6. EQUITY CURVE
==================================================

Create an equity curve for every strategy version.

Display:

- starting capital
- ending capital
- peak equity
- drawdowns
- recovery periods
- largest drawdown
- drawdown duration

Also show:

- equity curve before costs
- equity curve after costs

The after-cost curve is the primary result.

==================================================
7. MONTE CARLO / ROBUSTNESS TESTING
==================================================

Implement Monte Carlo analysis where appropriate.

Randomize trade sequence while preserving the tested trade-result distribution.

Estimate:

- possible drawdowns
- possible losing streaks
- expected equity ranges
- probability of severe drawdown

Do not use Monte Carlo to fabricate profitability.

Clearly label Monte Carlo as a statistical simulation.

==================================================
8. SAMPLE-SIZE WARNINGS
==================================================

Create minimum sample-size warnings.

UNDER 30 TRADES:
INSUFFICIENT SAMPLE

30-99:
LOW CONFIDENCE

100-299:
MODERATE SAMPLE

300+:
STRONGER SAMPLE

These are guidance labels, not claims of statistical certainty.

Never declare a strategy profitable solely because it has a high win rate.

==================================================
9. OUT-OF-SAMPLE TESTING
==================================================

Separate historical data into:

TRAINING
VALIDATION
OUT-OF-SAMPLE

The strategy must NOT be optimized using the out-of-sample period.

Show results separately.

Example:

TRAINING:
+X R

VALIDATION:
+Y R

OUT-OF-SAMPLE:
+Z R

If performance collapses out-of-sample:

FLAG:

POSSIBLE OVERFITTING

==================================================
10. WALK-FORWARD TESTING
==================================================

Implement chronological walk-forward testing.

Example:

TRAIN → TEST
TRAIN → TEST
TRAIN → TEST

Never allow future information to enter previous windows.

Show:

- number of windows
- profitable windows
- losing windows
- average window expectancy
- worst window
- best window
- consistency

A strategy must not depend on one unusually profitable period.

==================================================
11. PARAMETER ROBUSTNESS
==================================================

Allow controlled parameter sensitivity testing.

Example:

EMA:
18
19
20
21
22

ATR multiplier:
1.5
1.75
2.0
2.25
2.5

Do NOT optimize endlessly.

Create a parameter stability map.

If tiny parameter changes completely destroy performance:

FLAG:

FRAGILE STRATEGY

If nearby parameters produce similar results:

FLAG:

ROBUST PARAMETERS

==================================================
12. REGIME TESTING
==================================================

Test strategy performance separately during:

- TREND UP
- TREND DOWN
- RANGE
- BREAKOUT
- HIGH VOLATILITY
- LOW VOLATILITY

Display:

- trade count
- expectancy
- profit factor
- drawdown
- win rate

A strategy that only works in one regime must be explicitly labeled.

==================================================
13. SESSION ANALYSIS
==================================================

Break performance down by:

- ASIAN
- LONDON
- NEW YORK
- LONDON/NEW YORK OVERLAP

Allow configurable session definitions.

Identify whether performance is concentrated in one session.

Do not automatically conclude that the best historical session will remain the best in the future.

==================================================
14. NEWS ANALYSIS
==================================================

Separate trades into:

- NO HIGH-IMPACT NEWS
- BEFORE HIGH-IMPACT NEWS
- AFTER HIGH-IMPACT NEWS
- DURING HIGH-IMPACT NEWS

Compare performance.

Historical news classification must use only information that would have been available at the historical timestamp.

Do not leak future news information into historical decisions.

==================================================
15. PAIR ANALYSIS
==================================================

Compare strategy performance across supported OANDA forex instruments.

For each pair:

- trade count
- expectancy
- profit factor
- win rate
- drawdown
- average R

Do not assume a strategy works equally well on every pair.

==================================================
16. OVERFITTING DETECTION
==================================================

Create explicit warnings for:

- excellent training results + poor out-of-sample results
- very high parameter sensitivity
- small sample size
- performance concentrated in a tiny date range
- performance concentrated in one pair
- performance concentrated in one session
- performance dependent on unusually low costs

Display:

OVERFITTING RISK:
LOW / MEDIUM / HIGH

Explain why.

==================================================
17. STRATEGY SCORECARD
==================================================

Create a standardized scorecard:

- DATA QUALITY
- SAMPLE SIZE
- AFTER-COST EXPECTANCY
- PROFIT FACTOR
- MAX DRAWDOWN
- OUT-OF-SAMPLE
- WALK-FORWARD
- PARAMETER ROBUSTNESS
- REGIME ROBUSTNESS
- SESSION ROBUSTNESS
- PAIR ROBUSTNESS
- NEWS ROBUSTNESS
- EXECUTION SENSITIVITY

Create:

RESEARCH STATUS:
NOT READY
PROMISING
NEEDS MORE DATA
ROBUST
REJECTED

Do not call a strategy "PROFITABLE" based solely on backtest results.

==================================================
18. STRATEGY COMPARISON
==================================================

Allow:

Strategy A vs Strategy B vs Strategy C.

Compare:

- expectancy
- profit factor
- drawdown
- trade count
- win rate
- average R
- out-of-sample
- walk-forward
- cost sensitivity
- robustness

The comparison must use identical testing assumptions whenever possible.

==================================================
19. LIVE PERFORMANCE VALIDATION
==================================================

Once a strategy is deployed, compare:

BACKTEST
OUT-OF-SAMPLE
WALK-FORWARD
LIVE

Track live performance separately.

Never modify historical backtest results to match live performance.

Backtest data and live data must remain clearly separated.

==================================================
20. PERFORMANCE DRIFT DETECTION
==================================================

Detect when live performance materially deviates from tested expectations.

Monitor:

- rolling expectancy
- rolling win rate
- rolling average R
- rolling drawdown
- spread conditions
- market regime
- slippage
- execution quality

If deterioration becomes significant:

STRATEGY PERFORMANCE DRIFT

Then:

REDUCE/STOP NEW SIGNALS according to configurable safety rules.

Require user review before reactivation.

Do NOT automatically resume trading after drift.

==================================================
21. TRADE-QUALITY FEEDBACK LOOP
==================================================

For every completed live trade, record:

- original score
- technical conditions
- news conditions
- fundamental conditions
- regime
- spread
- entry
- slippage
- exit
- R
- P&L
- hold time
- exit reason

Compare predicted setup quality against actual outcome.

Do not automatically change strategy parameters based on a small number of trades.

Require statistically meaningful evidence before recommending changes.

==================================================
22. NO MARTINGALE
==================================================

Do NOT implement:

- martingale
- loss doubling
- revenge trading
- automatic position doubling after losses
- unlimited averaging down

==================================================
23. NO PROFIT GUARANTEE
==================================================

Never display:

GUARANTEED PROFIT
CERTAIN WIN
RISK-FREE TRADE
100% ACCURACY

Instead use:

HISTORICAL EXPECTANCY
DATA CONFIDENCE
SETUP SCORE
RISK STATUS
RESEARCH STATUS

==================================================
24. CAPITAL PRESERVATION
==================================================

Risk management takes priority over signal generation.

If:

- risk limit exceeded
- daily loss limit exceeded
- drawdown limit exceeded
- data quality fails
- execution quality deteriorates
- strategy drift detected

then:

BLOCK NEW TRADES

==================================================
25. STRATEGY DEPLOYMENT GATE
==================================================

Create a strategy deployment checklist.

A strategy cannot be marked:

READY FOR LIVE

unless configurable requirements are satisfied.

Minimum recommended checks:

- sufficient historical sample
- positive after-cost expectancy
- acceptable maximum drawdown
- out-of-sample test completed
- walk-forward test completed
- no major look-ahead/data leakage
- parameter robustness acceptable
- execution-cost sensitivity acceptable
- strategy rules documented
- risk limits configured

If requirements are not met:

NOT READY FOR LIVE

IMPORTANT:

READY FOR LIVE means the research/deployment checklist has passed.

It does NOT mean guaranteed profitability.

==================================================
26. RESEARCH REPORT
==================================================

Create a one-click strategy research report containing:

- Strategy
- Version
- Date range
- Pairs
- Timeframes
- Rules
- Parameters
- Trade count
- Win rate
- Average win
- Average loss
- Expectancy
- Profit factor
- Max drawdown
- Average R
- Costs
- Out-of-sample results
- Walk-forward results
- Monte Carlo results
- Parameter robustness
- Regime results
- Session results
- News results
- Overfitting risk
- Final research status

==================================================
27. DATA AND EXECUTION SEPARATION
==================================================

Strictly separate:

BACKTEST DATA
RESEARCH DATA
PAPER/RESEARCH RESULTS
LIVE OANDA DATA
LIVE OANDA TRADES

Backtesting must never call a live execution function.

Research code must never have an execution path that can accidentally submit a real order.

Live execution remains behind explicit user approval and backend revalidation.

==================================================
28. DATABASE DESIGN
==================================================

Inspect the existing Supabase schema first.

Add only the tables/columns/indexes required by this module.

Support persistent storage for:

- strategy definitions
- strategy versions
- strategy parameters
- datasets
- backtest runs
- trades
- R-multiples
- equity curves
- drawdowns
- Monte Carlo results
- OOS results
- walk-forward windows
- parameter sensitivity
- regime analysis
- session analysis
- news analysis
- pair analysis
- robustness results
- overfitting warnings
- deployment-gate results
- research reports
- live validation
- performance drift

Use appropriate foreign keys, indexes, constraints, timestamps, and row-level security.

Do not duplicate existing tables unnecessarily.

==================================================
29. SECURITY
==================================================

This is a private single-user trading application.

Maintain:

- authentication
- Supabase RLS
- server-side secrets
- secure OANDA credential handling
- no credentials in frontend
- no credentials in logs
- no credentials in research reports
- no credentials in Git commits

Research results must not expose sensitive account credentials.

==================================================
30. UI / STRATEGY RESEARCH LAB
==================================================

Add a professional Strategy Research Lab to the existing TradeScout AI interface.

Use the existing TradeScout AI design system.

Include:

- strategy list
- strategy status
- strategy versions
- create strategy
- duplicate/version strategy
- run backtest
- run OOS test
- run walk-forward
- run Monte Carlo
- parameter sensitivity
- regime analysis
- session analysis
- news analysis
- pair analysis
- scorecard
- equity curve
- R distribution
- drawdown chart
- comparison
- deployment gate
- research report

Clearly label:

BACKTEST
OUT-OF-SAMPLE
WALK-FORWARD
LIVE

Never visually imply that backtest results are live results.

==================================================
31. RESEARCH ENGINE ARCHITECTURE
==================================================

Do not put the entire backtesting engine inside React components.

Separate concerns appropriately.

Create reusable modules/services for:

- historical data
- event chronology
- strategy evaluation
- execution simulation
- cost model
- risk model
- metrics
- R analysis
- equity curve
- Monte Carlo
- OOS testing
- walk-forward
- parameter robustness
- regime analysis
- session analysis
- news analysis
- pair analysis
- overfitting detection
- deployment gate
- drift detection

Keep deterministic calculations deterministic.

Given identical:

- historical data
- strategy version
- parameters
- cost assumptions
- risk configuration

the same backtest should produce the same results.

==================================================
32. AUDIT TRAIL
==================================================

Every research run must record:

- strategy ID
- strategy version
- dataset ID/version
- date range
- instruments
- timeframes
- parameters
- cost assumptions
- risk assumptions
- software/engine version
- execution timestamp
- result status

Never overwrite previous research results.

==================================================
33. ERROR HANDLING
==================================================

If required historical data is missing:

DATA INSUFFICIENT

If data quality is invalid:

DATA QUALITY FAILED

If chronology cannot be guaranteed:

BACKTEST BLOCKED

If sample size is insufficient:

INSUFFICIENT SAMPLE

If costs cannot be modeled:

COST MODEL INCOMPLETE

Do not fabricate missing values.

Do not silently substitute fake data.

==================================================
34. TESTING REQUIREMENTS
==================================================

Create automated tests proving:

- future candles cannot affect past signals
- future news cannot affect past signals
- future economic events cannot affect past signals
- future fundamentals cannot affect past signals
- costs are included
- spread is included
- slippage assumptions are included
- commissions are included where configured
- swap/financing is included where configured
- out-of-sample data is isolated
- walk-forward chronology is correct
- strategy versions are immutable
- parameter changes create new versions
- paper/research results are separate from live
- live results are separate from backtests
- performance drift is detectable
- insufficient sample sizes are flagged
- overfitting warnings work
- rejected strategies cannot be deployed accidentally
- research cannot trigger live OANDA execution
- Monte Carlo does not alter original backtest results
- identical inputs produce reproducible results

==================================================
35. BUILD AND VALIDATION
==================================================

After implementation:

Run:

npm install

npm run build

npm test

If tests fail:

1. Investigate the failure.
2. Fix the implementation.
3. Re-run the tests.
4. Re-run the build.
5. Continue until the implemented functionality is actually validated.

Do not hide or suppress failing tests.

Do not delete tests simply because they fail.

==================================================
36. FINAL REPORT
==================================================

At the end, report exactly:

FILES CREATED

FILES MODIFIED

DATABASE CHANGES

MIGRATIONS CREATED

TEST RESULTS

BUILD RESULTS

STRATEGIES / ENGINES IMPLEMENTED

UI FEATURES IMPLEMENTED

SECURITY CHANGES

REMAINING CONFIGURATION

REMAINING LIMITATIONS

Do NOT claim:

"profitable"

"guaranteed"

"ready to make money"

unless the statement is explicitly qualified as historical research evidence.

Do not claim completion if required functionality is missing.

If something could not be implemented, clearly state what remains and why.

==================================================
37. FINAL ABSOLUTE RULE
==================================================

TradeScout AI must follow:

CAPITAL PRESERVATION FIRST.

DATA QUALITY OVER SIGNAL GENERATION.

EVIDENCE OVER ASSUMPTION.

NO TRADE OVER BAD TRADE.

BLOCK OVER UNCERTAIN EXECUTION.

BACKTEST EVIDENCE ≠ FUTURE PROFITABILITY.

LIVE EXECUTION REQUIRES EXPLICIT USER APPROVAL.

When evidence conflicts:

TRADESCOUT AI DOES NOT GUESS.

IT WAITS.
