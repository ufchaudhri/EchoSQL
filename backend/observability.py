"""
Observability for EchoSQL — OpenTelemetry tracing + structured JSON logging.

What gets written:
  backend/logs/app.jsonl     — every log line as JSON, with trace_id injected
  backend/logs/traces.jsonl  — every completed OTel span as JSON
  stdout                     — human-readable span summary + log lines

To also ship traces to Jaeger / Grafana Tempo / any OTLP backend:
  Set OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 in backend/.env
  Then open http://localhost:16686 (Jaeger UI) to browse traces.

Span hierarchy produced per request:
  POST /api/query  (FastAPIInstrumentor root span)
  └── echosql.query.process
      ├── echosql.cache.nl_lookup
      ├── echosql.llm.generate_sql
      │   └── ollama.http.generate       ← sub-span from llm_service.py
      ├── echosql.sql.validate
      ├── echosql.cache.sql_lookup
      ├── echosql.db.execute
      └── echosql.cache.write
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.resources import SERVICE_NAME as _OTEL_SVC_KEY
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

LOGS_DIR = Path(__file__).parent / "logs"


# ── Custom span exporter ─────────────────────────────────────────────────────

class _SpanExporter(SpanExporter):
    """
    For each completed span:
      • Prints a one-line human-readable summary to stdout.
      • Appends a full JSON record to backend/logs/traces.jsonl.
    """

    def __init__(self) -> None:
        LOGS_DIR.mkdir(exist_ok=True)
        self._path = LOGS_DIR / "traces.jsonl"

    def export(self, spans) -> SpanExportResult:
        for span in spans:
            rec = _span_to_dict(span)
            ok = rec["status"] != "ERROR"
            tag = "OK " if ok else "ERR"
            attrs = "  ".join(f"{k}={v}" for k, v in rec["attributes"].items())
            print(
                f"  ▸ [{tag}] {rec['trace_id'][:8]}  "
                f"{rec['name']:<42}  {rec['duration_ms']:>8.2f} ms"
                + (f"  {attrs}" if attrs else ""),
                flush=True,
            )
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def _span_to_dict(span) -> dict:
    ctx = span.context
    trace_id  = format(ctx.trace_id, "032x") if ctx else "0" * 32
    span_id   = format(ctx.span_id,  "016x") if ctx else "0" * 16
    parent_id = (
        format(span.parent.span_id, "016x")
        if span.parent and span.parent.span_id
        else None
    )
    t0 = span.start_time or 0
    t1 = span.end_time   or 0
    return {
        "timestamp":      datetime.fromtimestamp(t0 / 1e9, tz=timezone.utc).isoformat(),
        "trace_id":       trace_id,
        "span_id":        span_id,
        "parent_span_id": parent_id,
        "name":           span.name,
        "status":         span.status.status_code.name,
        "duration_ms":    round((t1 - t0) / 1e6, 2),
        "attributes":     dict(span.attributes or {}),
        "events": [
            {
                "name":  e.name,
                "ts":    datetime.fromtimestamp(e.timestamp / 1e9, tz=timezone.utc).isoformat(),
                "attrs": dict(e.attributes or {}),
            }
            for e in (span.events or [])
        ],
    }


# ── JSON log formatter ────────────────────────────────────────────────────────

_SKIP = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
})


class _JSONFormatter(logging.Formatter):
    """
    Emits every log record as a single JSON line.
    Injects the active OTel trace_id / span_id so log lines can be correlated
    with spans in traces.jsonl.
    """

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        ctx  = span.get_span_context() if span else None

        doc: dict = {
            "ts":     datetime.now(tz=timezone.utc).isoformat(),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
        }
        if ctx and ctx.is_valid:
            doc["trace_id"] = format(ctx.trace_id, "032x")
            doc["span_id"]  = format(ctx.span_id,  "016x")
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k not in _SKIP:
                doc[k] = v
        return json.dumps(doc, default=str)


# ── Public initialiser ────────────────────────────────────────────────────────

def configure_observability(service_name: str = "echosql") -> None:
    """
    Call once at startup (before the first request).

    Sets up:
      • Global OTel TracerProvider → writes spans to stdout + traces.jsonl
      • Python root logger        → JSON lines to stdout + app.jsonl
      • Optional OTLP exporter    → set OTEL_EXPORTER_OTLP_ENDPOINT in .env
    """
    LOGS_DIR.mkdir(exist_ok=True)

    # --- OTel provider ---
    resource = Resource.create({_OTEL_SVC_KEY: service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(_SpanExporter()))

    otlp = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp}/v1/traces"))
        )

    trace.set_tracer_provider(provider)

    # --- Python logging ---
    fmt = _JSONFormatter()

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)

    fh = RotatingFileHandler(
        LOGS_DIR / "app.jsonl",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(sh)
    root.addHandler(fh)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "sentence_transformers", "transformers", "torch"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Observability ready",
        extra={
            "service":  service_name,
            "logs_dir": str(LOGS_DIR),
            "otlp":     otlp or "disabled",
        },
    )
