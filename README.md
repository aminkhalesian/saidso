# Renewal Radar (working title)

Shows a CSM or account manager which renewals need them this week, why (in the customer's own words),
and a drafted next step they approve before anything is sent. One engine, swappable industry packs.
Synthetic data only; every company and person is fictional.

## Run it

Needs Python 3.9+ and Node 18+ (macOS: `brew install node`). Never commit `.env`; it holds the team key and is git-ignored.

```bash
./start.sh
```
Then open http://localhost:8000. The first run installs everything, builds the frontend and seeds the demo data.

To use the AI, put the team's OpenRouter key in `.env` (created from `.env.example` on first run), then reseed:
```bash
source .venv/bin/activate
cd backend
python -m app.cli seed                     # extraction + briefs with the AI (well under $1 per run)
python -m app.cli seed --llm-transcripts   # also let the AI write natural-sounding calls (~$1-2.50)
python -m app.cli seed --llm-emails        # also let the AI tailor the drafted emails
```
New OpenRouter accounts are limited to about 20 AI requests per minute, so a full AI seed (about 165 requests)
takes roughly 10-12 minutes; the app paces itself (`LLM_RPM` in `.env`, default 15) and retries when throttled.
Only one person on the team should run a seed at a time, since you all share the same key's limit.

Without a key everything runs offline with a naive keyword baseline, which is useful as a demo backup and as
the comparison on the Accuracy page. The live "Analyze a call" screen calls the AI on each click.

Frontend development with hot reload: `cd frontend && npm run dev` (port 5173, proxies `/api` to 8000).
Tests: `cd backend && python -m pytest`.

## How it's built

```
connectors/   synthetic.py, csv_folder.py  -> pull data, normalize, match billing names to accounts
engine/       extract.py   LLM extraction; drops any quote that isn't verbatim in a customer's turn
              scoring.py   transparent 0-100 score, weights from the pack
              brief.py     brief that may only cite numbered evidence; bad citations fall back to a template
              actions.py   drafted next steps from the pack's playbooks; nothing is sent without approval
              identity.py  name matching ("WEISSDORN INSURANCE GMBH" -> "Weißdorn Insurance")
              evaluate.py  precision / recall / decoys resisted against planted ground truth
packs/        saas.yaml, agency.yaml       -> everything industry-specific
models.py     canonical model; every row has client_id (SQLite default, DATABASE_URL for Postgres)
main.py       FastAPI: overview, renewals, account, actions, feedback, portfolio, trust, analyze
frontend/     React + Vite + Tailwind: My week, All renewals, Account, Portfolio, Accuracy, Analyze a call
```

## Adding an industry

Copy `backend/app/packs/agency.yaml` to a new file and change:
- `vocabulary`: what an account, a renewal, capacity and activity are called
- `signals`: the risk types, their weights, definitions (these become the AI prompt), keywords (offline
  fallback) and a playbook per signal
- `synthetic`: demo companies, the lines that plant each signal, and decoys that look risky but aren't

Add a client with that `pack_id` in `pipeline.DEMO_CLIENTS`, reseed, and the whole app speaks the new
industry, including its own Accuracy page. No engine code changes.

## Bring your own data (pilot)

```bash
python -m app.cli import-csv <client_id> path/to/folder
```
The folder holds `accounts.csv`, `contracts.csv`, `activity.csv` and `conversations.csv`; the column list is at the
top of `connectors/csv_folder.py`. Only use real customer data with the customer's permission, and never during
the hackathon (synthetic data only).

## For the design team

- All styling is Tailwind in `frontend/src`. Colors and fonts are tokens in `frontend/src/index.css` (`@theme`);
  change them there, not in components.
- Screens live in `frontend/src/pages`, shared pieces (risk pill, quote, citation chip, action card) in
  `frontend/src/components`.
- Run `cd frontend && npm run dev` with the backend running (`./start.sh` in another terminal) for live reload
  at http://localhost:5173.
- Words on screen come from the industry pack (`backend/app/packs/*.yaml` `vocabulary`), so test every change in
  both workspaces: Brightdesk (SaaS) and Kranich Studio (agency).
- `docs/screenshots` shows the first-pass screens from a live AI run (Portfolio is from offline data).
