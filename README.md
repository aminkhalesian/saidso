# saidso

**Don't guess who's leaving. They already said so.**

saidso is for customer success managers at B2B companies. It reads customer call transcripts with AI, ranks upcoming
renewals by churn risk, shows the exact customer quote behind each risk, and drafts next steps that the CSM approves
before anything is sent. One engine, swappable industry packs.

All data in this repository is synthetic. Every company and person is fictional.

## See it

| | |
|---|---|
| **Live link** (read-only snapshot, no install) | https://aminkhalesian.github.io/saidso/ |
| **One-file copy** (double-click, works offline) | `demo/saidso-offline.html` |
| **Full app** (AI, CSV import, call analysis) | `./start.sh`, then http://localhost:8000 |

The snapshot shows every screen with the pitch data. The CSV import and call analysis need the full app, because they
need a server, a database and an AI key.

## Run the full app

Needs Python 3.9+ and Node 18+ (macOS: `brew install node`).

```bash
./start.sh
```

The first start installs everything, builds the frontend and loads the demo database from `demo/engine.demo.db`.
Open http://localhost:8000. Without an AI key everything runs on an offline keyword baseline, which is also the
comparison shown on the Accuracy screen.

To use the AI, put an OpenRouter key in `.env` (copied from `.env.example` on first start; never commit it), then seed:

```bash
source .venv/bin/activate
cd backend
python -m app.cli seed                     # extraction, briefs and plans with the AI (well under $1)
python -m app.cli seed --llm-transcripts   # also let the AI write natural-sounding calls (about $1 to $2.50)
python -m app.cli seed --llm-emails        # also let the AI tailor drafted emails
```

New OpenRouter accounts allow about 20 AI requests per minute, so a full AI seed takes roughly 10 to 12 minutes. The app
paces itself (`LLM_RPM` in `.env`, default 15) and retries when throttled. Only one person should seed at a time.

Save the current state into the repo (database, offline copy and the Pages copy) with `./scripts/save_demo.sh`
(virtual environment active), then commit `demo/` and `docs/`.

## What is in the app

| Screen | What it does |
|---|---|
| **Dashboard** | Every high-risk renewal in the chosen horizon (30, 60 or 90 days), sortable by risk and renewal date, with the exact quote and a drafted next step to approve |
| **All renewals** | Every renewal in the horizon, filterable by risk level and sortable |
| **Retention analytics** | Ten KPIs in a leadership view and a CSM view. Each opens a drill-down with its definition, calculation and the customers behind the number |
| **Portfolio** | Where the money sits, by risk band |
| **Customer page** | Renewal brief, risk drivers, "Why this score", usage, support and billing evidence, every quote with a link to the full call, and a retention playbook |
| **Data sources** | The four kinds of data saidso reads and how each connects |
| **Accuracy** | Precision, recall and decoys resisted, measured against planted ground truth |
| **Analyze a call** | Paste a transcript for flags, or import a CSV of new customers and review them before adding |

## How it works

```
connectors/   synthetic.py, csv_folder.py, csv_import.py  -> pull data, normalise, match billing names to accounts
engine/       extract.py   AI extraction; drops any quote that is not verbatim in a customer turn
              scoring.py   transparent 0-100 score; weights come from the pack
              brief.py     brief and plan that may only cite numbered evidence; bad citations fall back to a template
              actions.py   drafted next steps from the pack's playbooks; nothing is sent without approval
              kpis.py      Retention analytics: each KPI with its definition, period and customer rows
              identity.py  name matching ("WEISSDORN INSURANCE GMBH" -> "Weissdorn Insurance")
              evaluate.py  precision, recall and decoys resisted against planted ground truth
packs/        saas.yaml, agency.yaml   everything industry-specific
plays/        full playbooks per signal, in plain YAML that people can edit
models.py     one model; every row carries client_id (SQLite by default, DATABASE_URL for Postgres)
main.py       FastAPI
frontend/     React, Vite, Tailwind
```

**The score** (0 to 100; 50 and above is High risk, 25 to 49 Watch) adds conversation signals (up to 35), usage trend (25),
seat or hours cut (10), unresolved support (10), payment issues (10) and renewal urgency (10), minus reassuring evidence
(up to 12). Weights live in each pack's `score:` block. Too little usage data is shown as "No data", never as zero.

**The AI is kept honest.** A risk flag is kept only if its quote appears word for word in a customer turn. Briefs and plans
may only cite numbered evidence. A reply with an unknown evidence id, a number that is not in the evidence, or a churn
probability is rejected, and the account falls back to a template built from the same evidence. Screens say whether text was
written by AI or by rules.

**Nothing is sent.** Approve records the decision. There are no integrations that contact a customer.

## Bring your own data

**CSV import (one file).** In the Analyze tab, upload one row per customer. Only `customer` is required. Put what the
customer said on a call in `call_notes`. Dates, numbers, separators and column names are tidied, and every fix is listed.
The upload waits for your decision: **Add to list** puts it on the Dashboard and in All renewals, **Decline** discards it.
"Download a template" gives the columns.

**CSV folder (pilot).** Eight files, one per source:

```bash
cd backend
python -m app.cli export-csv brightdesk ../pilot    # the files a customer would send
python -m app.cli import-csv brightdesk ../pilot    # run saidso on such a folder
```

The column list is at the top of `backend/app/connectors/csv_folder.py`. Use real customer data only with the customer's
permission.

## Adding an industry

Copy `backend/app/packs/agency.yaml` to a new file and change:

- `vocabulary`: what an account, a renewal, capacity and activity are called
- `signals`: risk types, weights, definitions (these become the AI prompt), keywords (offline fallback) and a playbook each
- `synthetic`: demo companies, the lines that plant each signal, and decoys that look risky but are not

Add a client with that `pack_id` in `pipeline.DEMO_CLIENTS` and reseed. The whole app, including its Accuracy page, speaks
the new industry. No engine code changes. After editing a play, `cd backend && python -m app.cli rebuild-actions` redrafts
actions without re-reading any call.

## Tests

```bash
cd backend && python -m pytest -q
```

Runs on a temporary database, so the demo database is never opened, and mocks the AI (no network). It covers detection,
scoring, evidence-cited briefs, the CSV import flow, Retention analytics (cards reconcile with their rows, horizons, missing
sources, client isolation) and the dashboard. `MOCK_LLM=0 LIVE_LLM=1 python -m pytest tests/test_live_llm.py -s` runs three
scenarios against the real model (needs a key; a few cents).

For frontend work: `cd frontend && npm run dev` (with the backend running) gives live reload at http://localhost:5173.
Colours and fonts are tokens in `frontend/src/index.css`. Words on screen come from the pack's `vocabulary`, so check
both workspaces: Brightdesk (SaaS) and Kranich Studio (agency).

## Known limits

- Synthetic data only. Real customer data is messier; column mapping and fuzzier files are still to do.
- No real integrations (CRM, billing, helpdesk, call recorder). Data comes in by CSV.
- No login or permissions.
- Revenue figures are scenarios from current contract values, not forecasts. True GRR, NRR, logo churn, NPS and CSAT need billing
  history or survey data. See [docs/whats-next.md](docs/whats-next.md).
- The shared Pages copy is read-only. Uploads and call analysis need the full app.
