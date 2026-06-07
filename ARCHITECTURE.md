# EchoSQL — Architectural Overview

> This document describes the conceptual design of the EchoSQL text-to-SQL application for the purpose of ongoing support and maintenance.

---

## 1. What the System Does

EchoSQL accepts a natural-language question (e.g. *"What is the total balance of all active accounts?"*), converts it to a PostgreSQL SELECT statement using a locally-running LLM, executes the query against a banking database, and returns the results as a table in the browser.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Browser (localhost:3000)                       │
│          Next.js frontend — query input + results table          │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP  POST /api/query[?explain=true]
                             │  HTTP  GET  /api/schema
                             │  HTTP  GET  /health
┌────────────────────────────▼────────────────────────────────────┐
│                FastAPI backend  (localhost:8000)                  │
│                                                                   │
│  routes/query.py       routes/schema.py    observability.py      │
│       │                                         │                │
│  services/             utils/             backend/logs/          │
│    llm_service.py        sql_validator.py    app.jsonl           │
│    db_service.py                              traces.jsonl       │
│    embedding_service.py                                          │
│    redis_cache.py                                                │
└───────┬──────────────┬──────────────────┬───────────────────────┘
        │              │                  │
   ┌────▼────┐   ┌─────▼──────┐   ┌──────▼──────┐
   │ Ollama  │   │ PostgreSQL │   │    Redis    │
   │ :11434  │   │   :5432    │   │   :6379     │
   │ (LLM)   │   │ (database) │   │  (cache)    │
   └─────────┘   └────────────┘   └─────────────┘

── Optional observability stack (Docker) ──────────────────────────
   ┌──────────────┐   ┌─────────┐   ┌──────────┐   ┌──────────┐
   │   Promtail   │   │  Loki   │   │  Tempo   │   │ Grafana  │
   │ (log shipper)│──▶│ :3100   │──▶│  :3200   │──▶│  :3001   │
   │ tails *.jsonl│   │ (logs)  │   │ (traces) │   │  (UI)    │
   └──────────────┘   └─────────┘   └──────────┘   └──────────┘
                                         ▲
                           OTLP (port 4318) from backend
```

All application processes run locally. The observability stack is optional and runs via a single Docker Compose command.

---

## 3. Components

### 3.1 Frontend — `frontend/`

Built with **Next.js 13 (Pages Router)** and TypeScript. The entire UI lives in a single-page app (`pages/index.tsx`) with four tabs.

| File | Role |
|------|------|
| `pages/index.tsx` | Single-page executive dashboard — all four tabs rendered inline. |
| `lib/api.ts` | HTTP client. `runQuery()` posts to `/api/query?explain=true`. Also provides `fetchHealth()` and `fetchSchema()` with a static schema fallback. |
| `styles/globals.css` | Full CSS design system — design tokens, layout, cards, tables, pipeline trace, shimmer, tab UI. No external CSS library. |

**Four tabs:**

| Tab | Components |
|-----|-----------|
| **Query Console** | Blue gradient hero with textarea + Cmd/Ctrl+Enter shortcut, example chips. On result: Executive Summary banner (LLM insight), confidence % chip, intent-match badge, source-table chips, cache/live badge, sortable results table, chart-type suggestion, proactive follow-up card with "Ask this" button, collapsible Technical Details with SQL viewer + pipeline trace timeline. |
| **Observability** | Health cards (API / PostgreSQL / Redis / Ollama) fetched live from `/health`. Expected latency table with inline bar charts per pipeline step. Link to Grafana dashboard. |
| **Schema & Help** | Usage tip cards, example query list with click-to-run, accordion schema browser for all five tables. Schema sourced from `GET /api/schema` with a static fallback. |
| **Architecture** | Executive overview (value props + flow diagram), component reference table, 7-step pipeline deep-dive with timing estimates. |

**Header:** Sticky dark navy bar with EchoSQL logo, tagline, and three live health dots (API / DB / LLM) updated on page load.

**Data flow:**

```
User types query → Cmd/Ctrl+Enter or Analyze button
    → runQuery(query) in lib/api.ts
    → POST /api/query?explain=true  { "query": "..." }
    ← { sql, rows, row_count, execution_time_ms, from_cache,
        source_tables, pipeline_steps, evaluation? }
    → Executive Summary, meta strip, DataTable, proactive card
    → TechDetails toggle → SQL viewer | PipelineTrace timeline
```

**Environment variable:** `NEXT_PUBLIC_API_BASE` (defaults to `http://localhost:8000`).

---

### 3.2 Backend — `backend/`

Built with **FastAPI** (Python 3.10+). Entry point is `main.py`.

#### Startup / shutdown

`main.py` calls `configure_observability()` before any other imports so that all log records and OTel spans use the configured provider from the first line of execution. FastAPI's `lifespan` context manager then opens the Redis connection on startup and closes it on shutdown. If Redis is unavailable the app continues without caching.

#### API surface

| Method | Path | Query params | Purpose |
|--------|------|-------------|---------|
| `POST` | `/api/query` | `?explain=true` | Convert NL → SQL → execute → return rows. With `?explain=true`, a second LLM call rates the SQL against the question (+1–2 s). |
| `GET` | `/api/schema` | — | Return DB schema grouped by table name |
| `GET` | `/health` | — | Report Redis / DB / Ollama status |

#### Service layer — `backend/services/`

| Module | Responsibility |
|--------|---------------|
| `llm_service.py` | Builds the schema-aware system prompt and calls Ollama. `generate_sql()` strips markdown fences and returns the first SELECT. `explain_sql(nl, sql)` fires a second prompt returning 6 fields: `score` (0-100), `match` (yes/partial/no), `explanation`, `executive_summary`, `chart_suggestion` (bar/line/pie/table), `proactive_question`. Timeout: 90 s / 30 s. |
| `db_service.py` | Opens a psycopg3 async connection per query, executes the SQL, and returns rows as `list[dict]`. Also provides `get_schema_info()` and `check_db_health()`. |
| `embedding_service.py` | Loads `all-MiniLM-L6-v2` lazily (first call only). Checks Redis before running inference; writes results back to Redis on a miss. Returns a normalised float list. |
| `redis_cache.py` | Wraps a `redis.Redis` client. Provides `cache_embedding` / `get_embedding` (key: `embedding:{md5}`, TTL: 24 h) and `cache_query_result` / `get_query_result` (key: `query_result:{md5}`, TTL: 5 min). Also exposes `get_stats()` for the health endpoint. |

#### Utility layer — `backend/utils/`

| Module | Responsibility |
|--------|---------------|
| `sql_validator.py` | Rejects any query that is not a SELECT. Uses sqlparse's token stream to block DML/DDL keywords (`DROP`, `DELETE`, `INSERT`, `UPDATE`, etc.). Also blocks stacked statements (bare semicolons inside the query body). |

#### Observability — `backend/observability.py`

Called once at import time in `main.py` before any other module is loaded. Sets up:
- A global OTel `TracerProvider` with a custom span exporter that writes completed spans to `backend/logs/traces.jsonl` and prints a one-line human-readable summary per span to stdout.
- The Python root logger configured to emit JSON lines (with `trace_id` / `span_id` injected from the active OTel span) to stdout and a rotating `backend/logs/app.jsonl`.
- An optional OTLP exporter (activated by `OTEL_EXPORTER_OTLP_ENDPOINT` in `.env`) that ships spans to Grafana Tempo.

#### Configuration — `backend/config.py` / `backend/.env`

| Variable | Default | Effect |
|----------|---------|--------|
| `DATABASE_URL` | `postgresql://postgres:…@localhost:5432/echosql` | psycopg3 connection string |
| `OLLAMA_MODEL` | `qwen:7b-chat-q4_K_M` | Model name passed to Ollama |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama base URL |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `REDIS_HOST` / `REDIS_PORT` | `localhost` / `6379` | Redis coordinates |
| `QUERY_RESULT_CACHE_TTL_MINUTES` | `5` | How long SQL results are cached |
| `EMBEDDING_CACHE_TTL_HOURS` | `24` | How long embeddings are cached |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(unset)* | Enable OTLP export to Grafana Tempo |

---

### 3.3 Database — `backend/database/`

**PostgreSQL 15** with the **pgvector** extension.

#### Banking domain tables (star schema)

```
customers ──< accounts >── branches
                 │
            transactions >── transaction_types
```

| Table | Rows (seeded) | Key columns |
|-------|--------------|-------------|
| `customers` | 100 000 | `name`, `email`, `account_type`, `kyc_status` |
| `branches` | 10 (static) | `city`, `state`, `country`, `manager_name` |
| `accounts` | 50 000 | `balance`, `status`, FK→customers, FK→branches |
| `transaction_types` | 15 (static) | `type_name`, `category` |
| `transactions` | 200 000 | `amount`, `balance_after`, `status`, FK→accounts, FK→transaction_types |

#### Supporting tables

| Table | Purpose |
|-------|---------|
| `query_cache` | Stores past NL queries + generated SQL + `vector(768)` embedding. Intended for pgvector semantic search (future use). |
| `schema_context` | 33 rows describing every column. Served by `GET /api/schema` and included in the LLM system prompt. |

#### Pre-built views

| View | Description |
|------|-------------|
| `customer_account_summary` | Per-customer account count, total balance, avg balance |
| `transaction_summary_by_type` | Count and amounts grouped by transaction type |
| `branch_performance` | Account/customer counts and balances per branch |

The LLM system prompt includes these views so the model can use them in generated queries.

---

### 3.4 LLM — Ollama

Ollama runs locally and exposes a REST API on port 11434. EchoSQL makes two types of calls:

| Call | Function | When |
|------|----------|------|
| SQL generation | `generate_sql(nl_query)` | Every cache-miss query |
| SQL evaluation | `explain_sql(nl_query, sql)` | Only when `?explain=true` is set, or during eval harness runs |

The SQL generation system prompt (in `llm_service.py`) contains the full schema, enum values, and pre-built views. The model is instructed to output only raw SQL. The response is post-processed by `_extract_sql()` which strips markdown fences and captures everything from the first `SELECT` keyword.

Ollama also returns internal performance counters (`eval_count`, `eval_duration`, `total_duration`, `load_duration`) which are captured as OTel span attributes on the `ollama.http.generate` span, making it easy to diagnose slow inference in Grafana.

**To change the model:** update `OLLAMA_MODEL` in `.env` and run `ollama pull <new-model>`. Re-run the eval harness to validate accuracy.

---

### 3.5 Redis Cache

Redis provides two independent cache layers:

| Layer | Key pattern | TTL | Short-circuits |
|-------|-------------|-----|---------------|
| NL query result | `nl_query:{md5(lower(query))}` | 5 min | LLM + DB |
| SQL result | `query_result:{md5(sql)}` | 5 min | DB only |
| Query embedding | `embedding:{md5(query)}` | 24 h | embedding model |

The NL cache is the fastest path — an identical question (case-insensitive) returns without touching Ollama or PostgreSQL.

Redis is **optional** — if unavailable at startup, all caches are bypassed silently.

---

## 4. Request Lifecycle (POST /api/query)

```
POST /api/query  { "query": "Show top 5 customers by balance" }
  [?explain=true adds step 8]
│
├─ 1. NL cache lookup  (Redis key: nl_query:{md5})
│     HIT  → return { sql, rows, from_cache: true }  ────────────────┐
│     MISS ↓                                                           │
│                                                                      │
├─ 2. LLM inference  (Ollama /api/generate, ~0.5–2 s)                 │
│     → span: echosql.llm.generate_sql                                 │
│       └─ span: ollama.http.generate  (captures token count, timing) │
│                                                                      │
├─ 3. SQL validation  (utils/sql_validator.py, <1 ms)                  │
│     → span: echosql.sql.validate                                     │
│     reject non-SELECT, DML/DDL keywords, stacked statements          │
│                                                                      │
├─ 4. SQL result cache lookup  (Redis key: query_result:{md5(sql)})   │
│     → span: echosql.cache.sql_lookup                                 │
│     HIT  → skip DB execution                                         │
│     MISS ↓                                                           │
│                                                                      │
├─ 5. Database execution  (psycopg3 async, ~50–500 ms)                 │
│     → span: echosql.db.execute                                       │
│     rows serialised: Decimal → float, datetime → str                │
│                                                                      │
├─ 6. Write caches  (nl_query + query_result keys)                     │
│     → span: echosql.cache.write                                      │
│                                                                      │
├─ 7. [optional] LLM self-evaluation  (?explain=true only, ~1–2 s)    │
│     → span: echosql.eval.explain_sql                                 │
│     returns { score: 0–100, match: yes|partial|no, explanation }     │
│                                                                      │
└─ 8. Return { sql, rows, row_count, execution_time_ms,               │
               from_cache [, evaluation] }  ──────────────────────────┘
```

Every span is a child of the HTTP root span created by `FastAPIInstrumentor`. All spans emit to `backend/logs/traces.jsonl` and optionally to Grafana Tempo via OTLP.

---

## 5. Observability

### Log files

| File | Format | Contents |
|------|--------|---------|
| `backend/logs/app.jsonl` | JSON lines, rotating 10 MB × 5 | Every application log record. Contains `trace_id` and `span_id` fields so lines can be correlated with spans. |
| `backend/logs/traces.jsonl` | JSON lines | Every completed OTel span: `trace_id`, `span_id`, `name`, `duration_ms`, `attributes`, `events`, `status`. |

### Span names and key attributes

| Span | Key attributes |
|------|---------------|
| `POST /api/query` | HTTP method, status code (FastAPI auto) |
| `echosql.query.process` | `query.text`, `query.total_ms`, `query.row_count`, `query.from_cache` |
| `echosql.cache.nl_lookup` | `cache.hit`, `latency_ms` |
| `echosql.llm.generate_sql` | `llm.model`, `llm.success`, `llm.latency_ms`, `llm.sql_preview` |
| `ollama.http.generate` | `llm.tokens_generated`, `llm.eval_duration_ms`, `llm.total_duration_ms`, `llm.load_duration_ms` |
| `echosql.sql.validate` | `sql.valid`, `sql.reject_reason` |
| `echosql.cache.sql_lookup` | `cache.hit`, `latency_ms` |
| `echosql.db.execute` | `db.system`, `db.statement`, `db.row_count`, `db.latency_ms` |
| `echosql.cache.write` | `cache.keys_written`, `latency_ms` |
| `echosql.eval.explain_sql` | `eval.score`, `eval.match` |

### Grafana observability stack (optional)

Start with one command from the project root:

```powershell
docker compose -f docker-compose.observability.yml up -d
```

| Container | Port | Purpose |
|-----------|------|---------|
| Promtail | — | Tails `app.jsonl` + `traces.jsonl` and ships to Loki |
| Loki | 3100 | Log aggregation backend |
| Tempo | 3200 / 4318 | Distributed trace backend; receives OTLP from the FastAPI backend |
| Grafana | **3001** | Dashboards. Loki and Tempo datasources and the EchoSQL dashboard are pre-provisioned. |

Grafana UI: **http://localhost:3001** (admin / admin) → open **Dashboards** in the left nav to find the pre-built **EchoSQL Observability** dashboard.

To enable live OTLP trace export from the backend to Tempo, add to `backend/.env`:
```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

**Useful LogQL queries in Grafana → Explore → Loki:**

| Query | What it shows |
|-------|--------------|
| `{job="echosql"}` | All log lines |
| `{job="echosql", level="ERROR"}` | Errors only |
| `{job="echosql"} \| json \| trace_id="<id>"` | One request end-to-end |
| `{job="echosql"} \| json \| total_ms > 2000` | Queries slower than 2 s |
| `{job="echosql"} \| json \| event="llm.complete"` | LLM completions |
| `{job="echosql"} \| json \| event=~"cache\\..*" \| hit="False"` | Cache misses |

---

## 6. Evaluation

The codebase has no automatic correctness guarantee — the LLM may produce SQL that is syntactically valid but semantically wrong. Two mechanisms address this:

### 6.1 On-demand explanation (per query)

Adding `?explain=true` to any query triggers a second Ollama call that rates the generated SQL:

```bash
POST /api/query?explain=true
{ "query": "top 5 customers by balance" }

# Response includes:
"evaluation": {
  "score": 88,          # 0–100 confidence
  "match": "yes",       # yes | partial | no
  "explanation": "This query joins customers and accounts, sums balances..."
}
```

This adds ~1–2 s latency and is off by default in normal use. It is always enabled in the eval harness.

### 6.2 Offline eval harness

`backend/eval/run_eval.py` runs 20 curated banking queries through the full pipeline and measures five metrics per query:

| Metric | What it checks |
|--------|---------------|
| `EXEC_OK` | Did the SQL execute without a database error? |
| `ROWS_OK` | Did it return at least one row? |
| `TABLES_OK` | Do all expected table names appear in the SQL? |
| `KEYWORDS_OK` | Are required SQL patterns present? Are blocked ones absent? |
| `EVAL_SCORE` | LLM self-assessment score (0–100) |

```powershell
cd backend
venv\Scripts\activate

python -m eval.run_eval                        # full eval, all 20 cases
python -m eval.run_eval --no-llm-eval          # skip LLM self-assessment (faster)
python -m eval.run_eval --ids simple_01,agg_05 # run specific cases
```

Results print to stdout and are saved to `backend/eval/results/eval_<timestamp>.json` for tracking improvement over time.

**Test case categories** (`backend/eval/test_cases.py`):

| Category | Count | Examples |
|----------|-------|---------|
| `simple` | 4 | "Show all customers", "List active accounts" |
| `aggregate` | 5 | "Total balance across all accounts", "How many customers?" |
| `join` | 4 | "Customer names with account balances", "Branch with most accounts" |
| `filter` | 3 | "Accounts over £50k", "Failed transactions" |
| `top-n` | 2 | "Top 5 customers by balance", "Top 10 largest transactions" |
| `date` | 2 | "Transactions last 7 days", "New customers this year" |

To improve accuracy, edit the `SCHEMA_PROMPT` constant in `backend/services/llm_service.py` and re-run the harness to compare scores.

---

## 7. File Tree (application code only)

```
echosql/
├── frontend/                         Next.js 13 frontend
│   ├── pages/
│   │   ├── index.tsx                 Main query console
│   │   ├── schema.tsx                Schema browser
│   │   ├── history.tsx               Query history
│   │   ├── admin.tsx                 Health dashboard
│   │   └── _app.tsx                  App wrapper
│   ├── components/
│   │   ├── QueryInput.tsx            NL input textarea + submit
│   │   ├── ResultsTable.tsx          Results table + SQL disclosure
│   │   └── QueryHistory.tsx          Past queries list (SWR)
│   ├── lib/
│   │   └── api.ts                    HTTP client for backend
│   └── package.json
│
├── backend/                          FastAPI Python backend
│   ├── main.py                       App factory, lifespan, health endpoint
│   ├── observability.py              OTel tracer + JSON logging setup
│   ├── config.py                     All env-var bindings
│   ├── requirements.txt
│   ├── .env                          Local secrets (not committed)
│   ├── .env.example                  Template
│   │
│   ├── routes/
│   │   ├── query.py                  POST /api/query (full pipeline + optional eval)
│   │   └── schema.py                 GET  /api/schema
│   │
│   ├── services/
│   │   ├── llm_service.py            Ollama client, SQL extraction, explain_sql()
│   │   ├── db_service.py             psycopg3 async query execution
│   │   ├── embedding_service.py      sentence-transformers + Redis cache
│   │   └── redis_cache.py            Redis client wrapper (embeddings + results)
│   │
│   ├── utils/
│   │   └── sql_validator.py          SELECT-only safety gate
│   │
│   ├── eval/
│   │   ├── test_cases.py             20 curated NL queries with expected SQL patterns
│   │   └── run_eval.py               Async batch eval harness + JSON results output
│   │
│   ├── logs/                         Written at runtime (not committed)
│   │   ├── app.jsonl                 Structured application logs (JSON lines)
│   │   └── traces.jsonl              Completed OTel spans (JSON lines)
│   │
│   └── database/
│       ├── schema.sql                DDL: tables, indexes, views, seed data
│       └── seed_data.py              Idempotent seeder — truncates + re-seeds on every run
│
├── observability/                    Config files for the Docker observability stack
│   ├── promtail.yml                  Promtail: tail app.jsonl + traces.jsonl → Loki
│   ├── tempo.yml                     Tempo: OTLP receiver + local trace storage
│   └── grafana/
│       └── provisioning/
│           └── datasources/
│               └── datasources.yml  Auto-provision Loki + Tempo in Grafana
│           └── dashboards/
│               ├── dashboards.yml   Dashboard provider config
│               └── echosql.json     Pre-built 13-panel EchoSQL dashboard
│
└── docker-compose.observability.yml  One-command Grafana + Loki + Promtail + Tempo
```

---

## 8. Key Design Decisions

**Local-only inference.** Ollama runs on the same machine; no data leaves the host. This keeps latency predictable and eliminates API costs, but requires a capable GPU for acceptable response times.

**Two-layer caching.** The NL-level cache (`nl_query:*`) short-circuits both the LLM and the database for repeated questions. The SQL-level cache (`query_result:*`) reuses DB results when the same SQL is generated from different phrasings. Both layers are bypassed gracefully when Redis is down.

**Strict SQL safety.** The validator allows only SELECT statements and checks every token before execution. The validator is the sole gatekeeper — no additional DB user privilege restriction is currently in place, so **the Postgres user in `.env` should have read-only access in production**.

**Lazy model loading.** `embedding_service.py` loads the sentence-transformers model on the first request rather than at startup, so the server comes up immediately even on slower machines.

**Stateless services.** Each service module (llm, db, embedding) is stateless except for `redis_cache.py` which holds a module-level singleton client. This makes individual services easy to test and replace independently.

**Observability initialised first.** `observability.py` is imported and `configure_observability()` is called at the top of `main.py` before any other application imports. This ensures every log line and OTel span produced anywhere in the codebase is captured from the very first request.

**No automatic correctness guarantee.** SQL validation checks safety, not semantics. The `?explain=true` parameter and the eval harness are the only mechanisms for assessing whether the generated SQL correctly answers the question. Running the eval harness regularly (e.g. after changing the model or system prompt) is the recommended way to track accuracy over time.

---

## 9. Common Maintenance Tasks

| Task | What to change |
|------|---------------|
| Switch LLM model | Set `OLLAMA_MODEL` in `.env`; run `ollama pull <model>`; re-run `python -m eval.run_eval` |
| Change DB password | Update `DATABASE_URL` in `backend/.env` |
| Tune cache TTLs | `QUERY_RESULT_CACHE_TTL_MINUTES` and `EMBEDDING_CACHE_TTL_HOURS` in `.env` |
| Add a new DB table | Add DDL to `schema.sql`; add rows to `schema_context`; update `SCHEMA_PROMPT` in `llm_service.py`; add eval cases to `eval/test_cases.py` |
| Add a frontend page | Create `frontend/pages/<name>.tsx`; add nav link in `_app.tsx` |
| Change backend port | Set `API_PORT` in `.env`; update `NEXT_PUBLIC_API_BASE` in the frontend |
| Clear the cache | `redis-cli flushdb` (clears all keys in db 0) |
| Re-seed the database | `python backend/database/seed_data.py` |
| Start observability stack | `docker compose -f docker-compose.observability.yml up -d` |
| Enable Tempo trace export | Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` in `backend/.env` |
| Run the eval harness | `cd backend && python -m eval.run_eval` |
| Improve SQL accuracy | Edit `SCHEMA_PROMPT` in `llm_service.py`; re-run eval to compare scores |
| View live logs | Open Grafana at http://localhost:3001 → Explore → Loki |
| Inspect a slow request | Copy `trace_id` from logs; paste in Grafana → Explore → Tempo |

---

## 10. Runtime Dependencies

| Service | Version | Role | Required? |
|---------|---------|------|-----------|
| PostgreSQL | 15+ with pgvector | Primary data store | Yes |
| Ollama | any | LLM inference host | Yes |
| Redis | 7+ | Two-layer result cache | No (graceful fallback) |
| Python | 3.10+ | Backend runtime | Yes |
| Node.js | 18+ | Frontend build/runtime | Yes |
| Docker | 24+ | Observability stack (Grafana/Loki/Tempo) | No (optional) |
