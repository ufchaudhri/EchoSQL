# EchoSQL Quick Start Guide

Get the full EchoSQL application running in ~30 minutes.

## Prerequisites

- Windows 10/11
- Python 3.10+ (`python --version`)
- Node.js 18+ (`node --version`)
- PostgreSQL 15 with the `pgvector` extension
- Ollama installed with `qwen:7b-chat-q4_K_M` pulled
- Redis 7+ installed and running

## Step 1: Redis Setup (5 minutes)

**Option A: Chocolatey (Recommended)**

```powershell
# Install Chocolatey first (if needed)
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Install Redis
choco install redis

# Verify
redis-cli ping
# Should return: PONG
```

**Option B: Direct Download**

- Download redis-windows 7.2.14, extract, and run `redis-server.exe`
- See [REDIS_SETUP.md](./REDIS_SETUP.md) for the direct download link

**Option C: Docker**

```powershell
docker run --name redis-echosql -d -p 6379:6379 redis:7.4.9
redis-cli ping  # Should return PONG
```

---

## Step 2: Backend Setup (10 minutes)

### 2.1 Create the environment file

```powershell
cd backend
Copy-Item .env.example .env
# Open .env and update DATABASE_URL with your Postgres password
```

### 2.2 Install Python dependencies

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
# Takes 3-5 minutes (sentence-transformers is large)
```

### 2.3 Verify the setup

```powershell
# All imports
python -c "import fastapi; import redis; import sentence_transformers; print('OK')"

# Redis connection
python -c "from services.redis_cache import get_redis_cache; cache = get_redis_cache(); cache.connect()"
# Should print: Connected to Redis at localhost:6379
```

---

## Step 3: Database Setup (15-20 minutes, first run only)

```powershell
# Create the database
createdb -U postgres echosql

# Load schema (tables, views, schema_context)
psql -U postgres -d echosql -f backend/database/schema.sql

# Seed ~350 000 rows (takes 5-10 minutes)
# Safe to re-run — truncates and re-seeds from scratch each time
python backend/database/seed_data.py
```

---

## Step 4: Frontend Setup (5 minutes)

```powershell
cd frontend
npm install
```

---

## Step 5: Start All Services

Open **4 terminal windows**:

**Terminal 1 — PostgreSQL**
```powershell
# Verify it's running
psql -U postgres -c "SELECT 1;"
# PostgreSQL typically runs as a Windows service automatically
```

**Terminal 2 — Ollama**
```powershell
ollama serve
# Should show: Listening on 127.0.0.1:11434
```

**Terminal 3 — FastAPI Backend**
```powershell
cd backend
venv\Scripts\activate
python -m uvicorn main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

**Terminal 4 — Next.js Frontend**
```powershell
cd frontend
npm run dev
# Opens http://localhost:3000
# Four tabs: Query Console · Observability · Schema & Help · Architecture
```

---

## Step 6 (Optional): Observability Stack

EchoSQL writes structured JSON logs and OpenTelemetry spans to `backend/logs/`. To explore them in Grafana with Loki (logs) and Tempo (traces), start the Docker stack:

```powershell
# From the project root
docker compose -f docker-compose.observability.yml up -d
```

Open **http://localhost:3001** (admin / admin). Go to **Dashboards** in the left nav — the **EchoSQL Observability** dashboard is pre-built with 13 panels covering query rate, end-to-end latency, LLM timing, cache hit/miss, and live log streams. Run a few queries through the frontend to populate the metric panels.

To stream live traces from the backend to Tempo, add this to `backend/.env` and restart the backend:
```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

**Useful log queries in Grafana → Explore → Loki:**

```logql
{job="echosql"}                                      # all logs
{job="echosql", level="ERROR"}                       # errors only
{job="echosql"} | json | event="llm.complete"        # LLM completions
{job="echosql"} | json | total_ms > 2000             # slow queries (>2 s)
```

To cross-link a log line to its trace: click the `trace_id` value — Grafana navigates to Tempo automatically.

---

## Verification Checklist

| Service | Command | Expected |
|---------|---------|----------|
| PostgreSQL | `psql -U postgres -c "SELECT 1;"` | Returns 1 |
| Redis | `redis-cli ping` | PONG |
| Ollama | `curl http://localhost:11434/api/tags` | JSON response |
| FastAPI | `curl http://localhost:8000/health` | JSON with status fields |
| Frontend | http://localhost:3000 | Executive dashboard loads (4 tabs) |
| Grafana (optional) | http://localhost:3001 | Dashboard loads |

---

## Access Points

| URL | What it is |
|-----|-----------|
| http://localhost:3000 | Query console |
| http://localhost:8000/docs | Swagger API explorer |
| http://localhost:8000/health | Service health JSON |
| http://localhost:3001 | Grafana (logs + traces, optional) |

---

## Running the Eval Harness

To check how accurately EchoSQL translates natural language to SQL, run the built-in harness of 20 curated banking queries:

```powershell
cd backend
venv\Scripts\activate

# Full evaluation (includes LLM self-assessment ~1-2 s per query)
python -m eval.run_eval

# Skip LLM self-assessment for a faster run
python -m eval.run_eval --no-llm-eval

# Run specific test cases
python -m eval.run_eval --ids simple_01,agg_01,join_03
```

Results print a colour-coded report to stdout and are saved to `backend/eval/results/eval_<timestamp>.json`.

---

## Troubleshooting

### Redis won't connect
```powershell
tasklist | findstr redis
redis-server   # start manually if not running
netstat -ano | findstr 6379
```

### FastAPI port already in use
```powershell
# Start on a different port
python -m uvicorn main:app --port 8001
```

### Ollama not responding
```powershell
curl http://localhost:11434/api/tags
ollama list    # check the model is pulled
ollama serve   # start if not running
```

### First-run embedding model download is slow
The `all-MiniLM-L6-v2` model (~90 MB) downloads from HuggingFace on the first query. Subsequent runs use the local cache.

### OTel packages not installed
```powershell
cd backend
venv\Scripts\activate
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http opentelemetry-instrumentation-fastapi
```

---

## Cache Inspection

```powershell
redis-cli keys "*"           # all keys
redis-cli keys "nl_query:*"  # NL query cache
redis-cli keys "query_result:*"  # SQL result cache
redis-cli keys "embedding:*" # embedding cache
redis-cli dbsize             # total key count
redis-cli flushdb            # clear all (use with care)
```

---

## Performance Expectations

| Scenario | Expected latency |
|----------|-----------------|
| NL cache hit (identical question) | < 100 ms |
| SQL cache hit (same SQL, different phrasing) | < 150 ms |
| Cache miss — LLM inference + DB execution | 600 ms – 3 s |
| `?explain=true` (LLM self-assessment) | add 1–2 s |

---

## Stop Services

```powershell
# Ctrl+C in each terminal, or:
taskkill /IM redis-server.exe /F
taskkill /IM ollama.exe /F

# Stop the Docker observability stack
docker compose -f docker-compose.observability.yml down
```
