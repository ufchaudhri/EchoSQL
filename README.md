# EchoSQL

EchoSQL converts natural-language questions into SQL, executes them against a local PostgreSQL banking database, and renders the results in a browser — all without any data leaving your machine.

## Components

| Directory | Role | Port |
|-----------|------|------|
| `frontend/` | Next.js executive dashboard — query console, observability, schema browser, architecture | 3000 |
| `backend/` | FastAPI backend — LLM orchestration, SQL generation, DB access | 8000 |
| `backend/database/` | PostgreSQL schema, views, and idempotent seed data script | 5432 |
| `backend/eval/` | Offline batch eval harness — 20 curated test cases | — |
| `observability/` | Grafana + Loki + Tempo configuration files (optional) | 3001 |

## Quick start

1. Start PostgreSQL (with pgvector), Redis, and Ollama — pull `qwen:7b-chat-q4_K_M` if not already done.
2. Set up the backend:
   ```powershell
   cd backend
   python -m venv venv; venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env   # edit DATABASE_URL with your Postgres password
   python -m uvicorn main:app --reload --port 8000
   ```
3. Load the database schema (first run only):
   ```powershell
   psql -U postgres -d echosql -f backend/database/schema.sql
   python backend/database/seed_data.py
   ```
4. Start the frontend:
   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

Open http://localhost:3000 and enter a natural-language question to try the system.

## Frontend — Executive Dashboard

The frontend is a single-page app with four tabs:

| Tab | What it shows |
|-----|--------------|
| **Query Console** | Search bar + example chips, Executive Summary card (LLM insight), confidence % + intent match + source tables, sortable results table, chart suggestion, proactive follow-up question, collapsible Technical Details (SQL + pipeline trace) |
| **Observability** | Real-time service health dots (API / DB / LLM), expected latency table per pipeline step, link to Grafana |
| **Schema & Help** | Usage tips, example queries, accordion schema browser for all tables |
| **Architecture** | Executive-audience overview, component reference table, 7-step pipeline deep-dive |

The header shows live health indicators (green/red dots) for the API, database, and LLM, updated on page load.

## Access points

| URL | What it is |
|-----|-----------|
| http://localhost:3000 | Query console (frontend) |
| http://localhost:8000/docs | Swagger API explorer |
| http://localhost:8000/health | Service health JSON |
| http://localhost:3001 | Grafana dashboards (optional, see below) |

## Observability (optional)

EchoSQL emits structured JSON logs and OpenTelemetry spans to `backend/logs/`. To view them in Grafana:

```powershell
docker compose -f docker-compose.observability.yml up -d
```

Open http://localhost:3001 (admin / admin) and go to **Dashboards** — the **EchoSQL Observability** dashboard is pre-built (query rate, latency, LLM timing, cache hits, log streams). Run a few queries through the frontend to see data populate.
To ship traces live from the backend to Tempo, add `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` to `backend/.env`.

## Evaluation

Run the built-in accuracy harness against 20 curated banking queries:

```powershell
cd backend
venv\Scripts\activate
python -m eval.run_eval              # full run
python -m eval.run_eval --no-llm-eval   # skip LLM self-assessment (faster)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for a complete technical reference and [QUICKSTART.md](QUICKSTART.md) for step-by-step setup.
