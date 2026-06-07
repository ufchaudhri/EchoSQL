"""
Query endpoint — converts natural language to SQL and executes it.

Pipeline steps returned in the response (pipeline_steps[]):
  1  NL Cache Lookup     — hit skips everything below
  2  LLM SQL Generation  — Ollama inference
  3  SQL Validation      — SELECT-only safety check
  4  SQL Cache Lookup    — hit skips DB execution
  5  Database Execution  — psycopg3 async query
  6  Cache Write         — store results in Redis
  7  LLM Evaluation      — explain=true only
"""

import decimal
import datetime
import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from config import QUERY_RESULT_CACHE_TTL_MINUTES, OLLAMA_MODEL
from services.db_service import execute_query
from services.llm_service import explain_sql, generate_sql
from services.redis_cache import get_redis_cache
from utils.sql_validator import validate_sql

logger = logging.getLogger(__name__)
router = APIRouter()
tracer = trace.get_tracer(__name__)

_NL_CACHE_TTL = QUERY_RESULT_CACHE_TTL_MINUTES * 60


class QueryRequest(BaseModel):
    query: str


def _nl_key(text: str) -> str:
    return f"nl_query:{hashlib.md5(text.lower().strip().encode()).hexdigest()}"


def _serialize(rows: List[Dict]) -> List[Dict]:
    out = []
    for row in rows:
        clean: Dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, decimal.Decimal):
                clean[k] = float(v)
            elif isinstance(v, (datetime.datetime, datetime.date)):
                clean[k] = str(v)
            else:
                clean[k] = v
        out.append(clean)
    return out


def _extract_tables(sql: str) -> List[str]:
    """Extract table/view names referenced in a SQL statement."""
    raw = re.findall(r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql, re.IGNORECASE)
    skip = {'where', 'on', 'as', 'with', 'select', 'having', 'group', 'order',
            'limit', 'offset', 'by', 'inner', 'outer', 'left', 'right', 'cross', 'full'}
    seen: set = set()
    result = []
    for t in raw:
        tl = t.lower()
        if tl not in skip and tl not in seen:
            seen.add(tl)
            result.append(t)
    return result


def _step(name: str, status: str, latency_ms: float, detail: str = "") -> Dict:
    return {"name": name, "status": status, "latency_ms": round(latency_ms, 2), "detail": detail}


@router.post("/api/query")
async def run_query(req: QueryRequest, explain: bool = False):
    """
    Convert a natural-language question to SQL and return the results.

    Query param: ?explain=true  — adds a second LLM call that rates how well
    the generated SQL matches the question (~1-2 s extra latency).

    Response includes pipeline_steps[] and source_tables[] for UI transparency.
    """
    user_query = req.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="query field cannot be empty")

    cache = get_redis_cache()
    pipeline_steps: List[Dict] = []

    with tracer.start_as_current_span("echosql.query.process") as root:
        root.set_attribute("query.text", user_query[:300])
        t0 = time.perf_counter()

        logger.info("Query received", extra={"event": "query.start", "query": user_query})

        # ── 1. NL cache lookup ──────────────────────────────────────────────────
        nl_key = _nl_key(user_query)
        t_step = time.perf_counter()
        cached = None

        with tracer.start_as_current_span("echosql.cache.nl_lookup") as span:
            if cache.client:
                try:
                    raw = cache.client.get(nl_key)
                    if raw:
                        cached = json.loads(raw)
                except Exception as e:
                    logger.warning("NL cache read error", extra={"error": str(e)})
            hit = cached is not None
            step_ms = (time.perf_counter() - t_step) * 1000
            span.set_attribute("cache.hit", hit)
            span.set_attribute("latency_ms", step_ms)

        pipeline_steps.append(_step(
            "NL Cache Lookup",
            "hit" if hit else "miss",
            step_ms,
            "Returned cached result — skipped LLM and DB" if hit else "No cache entry found",
        ))
        logger.info("cache.nl_lookup",
                    extra={"event": "cache.nl_lookup", "hit": hit, "latency_ms": step_ms})

        if cached:
            total_ms = (time.perf_counter() - t0) * 1000
            root.set_attribute("query.from_cache", True)
            root.set_attribute("query.total_ms", total_ms)
            root.set_attribute("query.row_count", len(cached["rows"]))
            logger.info("Query complete", extra={"event": "query.complete", "from_cache": True,
                        "row_count": len(cached["rows"]), "total_ms": total_ms})

            evaluation = None
            if explain and cached.get("sql"):
                with tracer.start_as_current_span("echosql.eval.explain_sql") as span:
                    t_eval = time.perf_counter()
                    evaluation = await explain_sql(user_query, cached["sql"])
                    eval_ms = (time.perf_counter() - t_eval) * 1000
                    span.set_attribute("eval.score", evaluation.get("score") or -1)
                    pipeline_steps.append(_step("LLM Evaluation", "ok", eval_ms,
                                                f"Confidence: {evaluation.get('score')}%"))

            return {
                "sql":               cached["sql"],
                "rows":              cached["rows"],
                "row_count":         len(cached["rows"]),
                "execution_time_ms": round(total_ms, 2),
                "from_cache":        True,
                "source_tables":     _extract_tables(cached["sql"]),
                "pipeline_steps":    pipeline_steps,
                **({"evaluation": evaluation} if evaluation else {}),
            }

        # ── 2. LLM SQL generation ───────────────────────────────────────────────
        t_step = time.perf_counter()
        logger.info("LLM generation starting", extra={"event": "llm.start", "model": OLLAMA_MODEL})
        generated_sql = None

        with tracer.start_as_current_span("echosql.llm.generate_sql") as span:
            span.set_attribute("llm.model", OLLAMA_MODEL)
            generated_sql = await generate_sql(user_query)
            step_ms = (time.perf_counter() - t_step) * 1000
            span.set_attribute("llm.success", generated_sql is not None)
            span.set_attribute("llm.latency_ms", step_ms)
            if generated_sql:
                span.set_attribute("llm.sql_preview", generated_sql[:300])
            else:
                span.set_status(StatusCode.ERROR, "no SQL returned")

        pipeline_steps.append(_step(
            "LLM SQL Generation",
            "ok" if generated_sql else "error",
            step_ms,
            f"Model: {OLLAMA_MODEL}" if generated_sql else "No SQL returned",
        ))
        logger.info("LLM generation complete",
                    extra={"event": "llm.complete", "success": generated_sql is not None,
                           "sql": (generated_sql or "")[:300], "latency_ms": step_ms})

        if not generated_sql:
            root.set_status(StatusCode.ERROR, "SQL generation failed")
            raise HTTPException(status_code=503,
                                detail="SQL generation failed — is `ollama serve` running?")

        # ── 3. SQL validation ───────────────────────────────────────────────────
        t_step = time.perf_counter()

        with tracer.start_as_current_span("echosql.sql.validate") as span:
            ok, reason = validate_sql(generated_sql)
            step_ms = (time.perf_counter() - t_step) * 1000
            span.set_attribute("sql.valid", ok)
            span.set_attribute("latency_ms", step_ms)
            if not ok:
                span.set_attribute("sql.reject_reason", reason)
                span.set_status(StatusCode.ERROR, reason)

        pipeline_steps.append(_step(
            "SQL Validation",
            "ok" if ok else "error",
            step_ms,
            "SELECT-only check passed" if ok else f"Rejected: {reason}",
        ))
        logger.info("SQL validation",
                    extra={"event": "sql.validate", "valid": ok,
                           "reason": reason or None, "latency_ms": step_ms})

        if not ok:
            root.set_status(StatusCode.ERROR, f"SQL rejected: {reason}")
            raise HTTPException(status_code=422,
                                detail=f"Generated SQL failed safety check: {reason}")

        # ── 4. SQL result cache lookup ──────────────────────────────────────────
        t_step = time.perf_counter()
        rows: List[Dict] = []
        from_sql_cache = False

        with tracer.start_as_current_span("echosql.cache.sql_lookup") as span:
            if cache.client:
                hit_data = cache.get_query_result(generated_sql)
                if hit_data:
                    rows = hit_data["result"]
                    from_sql_cache = True
            step_ms = (time.perf_counter() - t_step) * 1000
            span.set_attribute("cache.hit", from_sql_cache)
            span.set_attribute("latency_ms", step_ms)

        pipeline_steps.append(_step(
            "SQL Cache Lookup",
            "hit" if from_sql_cache else "miss",
            step_ms,
            "Reused cached result set" if from_sql_cache else "No cached result for this SQL",
        ))
        logger.info("cache.sql_lookup",
                    extra={"event": "cache.sql_lookup", "hit": from_sql_cache,
                           "latency_ms": step_ms})

        # ── 5. DB execution ─────────────────────────────────────────────────────
        db_ms = 0.0
        if not from_sql_cache:
            t_step = time.perf_counter()
            logger.info("DB execution starting",
                        extra={"event": "db.start", "sql": generated_sql[:300]})

            with tracer.start_as_current_span("echosql.db.execute") as span:
                span.set_attribute("db.system", "postgresql")
                span.set_attribute("db.statement", generated_sql[:500])
                try:
                    raw_rows = await execute_query(generated_sql)
                    rows = _serialize(raw_rows)
                    db_ms = (time.perf_counter() - t_step) * 1000
                    span.set_attribute("db.row_count", len(rows))
                    span.set_attribute("db.latency_ms", db_ms)
                except ValueError as e:
                    db_ms = (time.perf_counter() - t_step) * 1000
                    span.set_status(StatusCode.ERROR, str(e))
                    root.set_status(StatusCode.ERROR, str(e))
                    pipeline_steps.append(_step("Database Execution", "error", db_ms, str(e)))
                    logger.error("DB execution failed",
                                 extra={"event": "db.error", "error": str(e), "latency_ms": db_ms})
                    raise HTTPException(status_code=422, detail=str(e))

            pipeline_steps.append(_step(
                "Database Execution",
                "ok",
                db_ms,
                f"{len(rows)} row{'s' if len(rows) != 1 else ''} returned",
            ))
            logger.info("DB execution complete",
                        extra={"event": "db.complete", "row_count": len(rows),
                               "latency_ms": db_ms})
        else:
            pipeline_steps.append(_step("Database Execution", "skip", 0,
                                        "Skipped — result loaded from SQL cache"))

        # ── 6. Write caches ─────────────────────────────────────────────────────
        if cache.client and not from_sql_cache:
            t_step = time.perf_counter()
            with tracer.start_as_current_span("echosql.cache.write") as span:
                try:
                    cache.cache_query_result(generated_sql, rows,
                                             ttl_minutes=QUERY_RESULT_CACHE_TTL_MINUTES)
                    cache.client.setex(nl_key, _NL_CACHE_TTL,
                                       json.dumps({"sql": generated_sql, "rows": rows}))
                    step_ms = (time.perf_counter() - t_step) * 1000
                    span.set_attribute("cache.keys_written", 2)
                    pipeline_steps.append(_step("Cache Write", "ok", step_ms,
                                                "Stored NL result + SQL result"))
                except Exception as e:
                    logger.warning("Cache write failed", extra={"error": str(e)})

        # ── 7. LLM evaluation (optional) ────────────────────────────────────────
        total_ms = (time.perf_counter() - t0) * 1000
        root.set_attribute("query.from_cache", from_sql_cache)
        root.set_attribute("query.total_ms", total_ms)
        root.set_attribute("query.row_count", len(rows))

        logger.info("Query complete",
                    extra={"event": "query.complete", "row_count": len(rows),
                           "total_ms": total_ms, "from_cache": from_sql_cache,
                           "sql": generated_sql[:300] if generated_sql else ""})

        evaluation = None
        if explain and generated_sql:
            with tracer.start_as_current_span("echosql.eval.explain_sql") as span:
                t_eval = time.perf_counter()
                evaluation = await explain_sql(user_query, generated_sql)
                eval_ms = (time.perf_counter() - t_eval) * 1000
                span.set_attribute("eval.score", evaluation.get("score") or -1)
                span.set_attribute("eval.match", evaluation.get("match", "unknown"))
                pipeline_steps.append(_step("LLM Evaluation", "ok", eval_ms,
                                            f"Confidence: {evaluation.get('score')}%"))
            logger.info("SQL evaluation", extra={"event": "eval.complete", **evaluation})

        return {
            "sql":               generated_sql,
            "rows":              rows,
            "row_count":         len(rows),
            "execution_time_ms": round(total_ms, 2),
            "from_cache":        from_sql_cache,
            "source_tables":     _extract_tables(generated_sql),
            "pipeline_steps":    pipeline_steps,
            **({"evaluation": evaluation} if evaluation else {}),
        }
