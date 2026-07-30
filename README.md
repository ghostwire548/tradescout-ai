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
