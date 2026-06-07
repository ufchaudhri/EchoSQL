# EchoSQL Setup Summary

EchoSQL is a fully implemented local text-to-SQL application. This document summarises all components, their current status, and how to run them.

---

## Project Structure

```
echosql/
├── frontend/                    Next.js TypeScript frontend
│   ├── pages/
│   │   ├── index.tsx            Query console (main UI)
│   │   ├── schema.tsx           Schema browser
│   │   ├── history.tsx          Query history
│   │   ├── admin.tsx            Health dashboard
│   │   └── _app.tsx
│   ├── components/
│   │   ├── QueryInput.tsx       NL input + submit
│   │   ├── ResultsTable.tsx     Results table + SQL disclosure
│   │   └── QueryHistory.tsx     Past queries (SWR)
│   ├── lib/api.ts               HTTP client for backend
│   └── package.json
│
├── backend/                     FastAPI Python backend
│   ├── main.py                  App factory, lifespan, health endpoint
│   ├── observability.py         OpenTelemetry tracing + JSON logging
│   ├── config.py                All environment-variable bindings
│   ├── requirements.txt
│   ├── .env                     Local secrets (not committed)
│   ├── .env.example             Environment template
│   │
│   ├── routes/
│   │   ├── query.py             POST /api/query  (full NL→SQL pipeline)
│   │   └── schema.py            GET  /api/schema
│   │
│   ├── services/
│   │   ├── llm_service.py       Ollama client, SQL extraction, explain_sql()
│   │   ├── db_service.py        psycopg3 async query execution
│   │   ├── embedding_service.py sentence-transformers + Redis cache
│   │   └── redis_cache.py       Redis client wrapper (embeddings + results)
│   │
│   ├── utils/
│   │   └── sql_validator.py     SELECT-only safety gate
│   │
│   ├── eval/
│   │   ├── test_cases.py        20 curated NL queries with expected SQL patterns
│   │   └── run_eval.py          Async batch eval harness
│   │
│   ├── logs/                    Runtime output (not committed)
│   │   ├── app.jsonl            Structured JSON application logs
│   │   └── traces.jsonl         Completed OTel spans
│   │
│   └── database/
│       ├── schema.sql           DDL: tables, views, indexes, schema_context
│       └── seed_data.py         Idempotent seeder — truncates + re-seeds on every run
│
├── observability/               Docker observability stack config
│   ├── promtail.yml             Tails app.jsonl + traces.jsonl → Loki
│   ├── tempo.yml                OTLP receiver + local trace storage
│   └── grafana/
│       └── provisioning/
│           └── datasources/
│               └── datasources.yml  Loki + Tempo auto-provisioning
│           └── dashboards/
│               ├── dashboards.yml   Dashboard provider config
│               └── echosql.json     Pre-built EchoSQL dashboard
│
├── docker-compose.observability.yml  One-command Grafana/Loki/Promtail/Tempo
├── ARCHITECTURE.md              Full technical reference
├── QUICKSTART.md                Step-by-step setup guide
├── REDIS_SETUP.md               Redis installation options
└── README.md                    Project overview
```

---

## Core Components

### 1. Frontend (Next.js) — `frontend/`
- **Port**: http://localhost:3000
- **Pages**: query console, schema browser, query history, health admin
- **API client**: `lib/api.ts` posts to `POST /api/query`, uses SWR for `GET` endpoints

### 2. Backend (FastAPI) — `backend/`
- **Port**: http://localhost:8000
- **Endpoints**:

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/api/query` | NL → SQL → execute. Add `?explain=true` for LLM self-assessment. |
| `GET`  | `/api/schema` | Returns schema grouped by table name |
| `GET`  | `/health` | Redis / DB / Ollama status |
| `GET`  | `/docs` | Swagger UI |

### 3. Database (PostgreSQL) — `backend/database/`
- **Port**: localhost:5432 / database: `echosql`
- **Schema**: 5 banking tables + 2 embedding tables + 3 pre-built views
- **Data**: ~350 000 seeded rows (100k customers, 50k accounts, 200k transactions)
- **Extension**: pgvector for embedding columns

### 4. LLM Inference (Ollama)
- **Port**: http://localhost:11434
- **Model**: `qwen:7b-chat-q4_K_M` (default)
- **Two call types**: SQL generation (every cache miss) and SQL self-evaluation (`?explain=true`)

### 5. Cache (Redis)
- **Port**: localhost:6379
- **Three cache layers**:

| Layer | Key pattern | TTL |
|-------|-------------|-----|
| NL query result | `nl_query:{md5}` | 5 min |
| SQL result | `query_result:{md5}` | 5 min |
| Embeddings | `embedding:{md5}` | 24 h |

### 6. Observability — `backend/observability.py` + `observability/`
- **Log files**: `backend/logs/app.jsonl` (application logs) and `backend/logs/traces.jsonl` (OTel spans) — both JSON lines, rotating 10 MB × 5
- **Trace IDs**: injected into every log record so logs and spans can be correlated
- **Grafana stack** (optional, Docker): Loki (logs), Tempo (traces), Promtail (log shipper), Grafana UI on port 3001. The **EchoSQL Observability** dashboard is pre-provisioned — open Dashboards in the left nav after starting the stack.
- **OTLP export**: enabled by setting `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` in `.env`

### 7. Evaluation — `backend/eval/`
- **20 curated test cases** across 6 categories: simple, aggregate, join, filter, top-n, date
- **5 metrics per case**: EXEC_OK, ROWS_OK, TABLES_OK, KEYWORDS_OK, EVAL_SCORE (LLM self-assessment)
- **Results saved** to `backend/eval/results/eval_<timestamp>.json`

---

## Installation Checklist

### Phase 1: Prerequisites

- [ ] PostgreSQL 15 with pgvector — `psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"`
- [ ] Ollama with model — `ollama pull qwen:7b-chat-q4_K_M`
- [ ] Redis — `redis-cli ping` returns PONG
- [ ] Python 3.10+ — `python --version`
- [ ] Node.js 18+ — `node --version`
- [ ] Docker (optional, for observability stack)

### Phase 2: Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env: set DATABASE_URL password
```

### Phase 3: Database (first run only)

```powershell
createdb -U postgres echosql
psql -U postgres -d echosql -f backend/database/schema.sql
python backend/database/seed_data.py
```

### Phase 4: Frontend

```powershell
cd frontend
npm install
```

---

## Startup Sequence

**Terminal 1 — PostgreSQL** (usually auto-starts as a Windows service)
```powershell
psql -U postgres -c "SELECT 1;"
```

**Terminal 2 — Redis**
```powershell
redis-server   # or it starts automatically if installed as a service
```

**Terminal 3 — Ollama**
```powershell
ollama serve
```

**Terminal 4 — FastAPI Backend**
```powershell
cd backend
venv\Scripts\activate
python -m uvicorn main:app --reload --port 8000
```

**Terminal 5 — Next.js Frontend**
```powershell
cd frontend
npm run dev
```

**Optional — Grafana Observability Stack**
```powershell
docker compose -f docker-compose.observability.yml up -d
```

---

## Health Checks

```powershell
# PostgreSQL
psql -U postgres -d echosql -c "SELECT COUNT(*) FROM customers;"

# Redis
redis-cli ping

# Ollama
curl http://localhost:11434/api/tags

# FastAPI
curl http://localhost:8000/health

# Frontend
# Open http://localhost:3000

# Grafana (optional)
# Open http://localhost:3001
```

---

## Running the Eval Harness

```powershell
cd backend
venv\Scripts\activate

python -m eval.run_eval                          # all 20 cases + LLM self-eval
python -m eval.run_eval --no-llm-eval            # skip self-eval (faster)
python -m eval.run_eval --ids simple_01,join_03  # specific cases
```

---

## Performance Expectations

| Scenario | Latency |
|----------|---------|
| NL cache hit | < 100 ms |
| SQL cache hit | < 150 ms |
| Cache miss (LLM + DB) | 600 ms – 3 s |
| `?explain=true` overhead | +1–2 s |

---

## Troubleshooting Quick Reference

| Issue | Resolution |
|-------|-----------|
| FK violation during seeding | Re-run `seed_data.py` — it truncates first and uses real IDs, so this cannot recur |
| Seeding errored mid-run | Re-run — the script is idempotent (truncates + restarts sequences every run) |
| Password auth failed (Postgres) | Update `DATABASE_URL` in `backend/.env` |
| Redis won't connect | Run `redis-server` / `redis-cli ping` |
| Ollama model not found | `ollama pull qwen:7b-chat-q4_K_M` |
| OTel import errors | `pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http opentelemetry-instrumentation-fastapi` |
| Grafana port conflict | Grafana is mapped to 3001 (not 3000) by design |
| Embedding model slow | First call downloads ~90 MB; subsequent calls use local cache |
| Port already in use | Set `API_PORT` in `.env` or add `--port 8001` to uvicorn command |

---

## Documentation Index

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Full technical reference — components, request lifecycle, observability, eval, file tree |
| [QUICKSTART.md](QUICKSTART.md) | Step-by-step setup with observability and eval sections |
| [REDIS_SETUP.md](REDIS_SETUP.md) | Redis installation options |
| [backend/config.py](backend/config.py) | All configurable environment variables |

---

**Status**: Implementation complete. All backend services, frontend components, observability pipeline, and eval harness are implemented and functional.
