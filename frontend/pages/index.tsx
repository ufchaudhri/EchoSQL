import { useState, useEffect, useMemo, useRef, KeyboardEvent } from "react";
import {
  runQuery,
  fetchHealth,
  fetchSchema,
  QueryResult,
  HealthStatus,
  SchemaTable,
  PipelineStep,
} from "../lib/api";

// ─── Constants ────────────────────────────────────────────────────────────────

const EXAMPLE_QUERIES = [
  "Top 10 customers by total balance",
  "Monthly transaction volume for last 6 months",
  "Branches with most frozen accounts",
  "Average balance by account type",
  "Failed transactions in the last 30 days",
];

const TABS = ["Query Console", "Observability", "Schema & Help", "Architecture"] as const;
type Tab = (typeof TABS)[number];

const CHART_ICONS: Record<string, string> = {
  bar: "■",
  line: "∿",
  pie: "◕",
  table: "▤",
};

const STEP_LABELS: Record<string, string> = {
  ok: "OK",
  hit: "HIT",
  miss: "MISS",
  skip: "SKIP",
  error: "ERR",
};

// ─── Helper components ────────────────────────────────────────────────────────

function Shimmer({ rows = 4 }: { rows?: number }) {
  return (
    <div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="loading-shimmer" style={{ width: `${70 + (i % 3) * 10}%` }} />
      ))}
    </div>
  );
}

function ScoreChip({ score }: { score: number | null }) {
  if (score === null) return null;
  const cls =
    score >= 80 ? "score-high" : score >= 50 ? "score-med" : "score-low";
  return (
    <span className={`meta-chip ${cls}`}>
      <span className="meta-dot" />
      {score}% confidence
    </span>
  );
}

// ─── Sortable table ───────────────────────────────────────────────────────────

function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  if (!rows.length)
    return <p style={{ color: "var(--gray-400)", fontSize: 13, padding: 16 }}>No rows returned.</p>;

  const cols = Object.keys(rows[0]);

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => {
      const va = a[sortKey] ?? "";
      const vb = b[sortKey] ?? "";
      const cmp =
        typeof va === "number" && typeof vb === "number"
          ? va - vb
          : String(va).localeCompare(String(vb), undefined, { numeric: true });
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [rows, sortKey, sortDir]);

  function handleSort(col: string) {
    if (col === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col);
      setSortDir("asc");
    }
  }

  function isNum(v: unknown) {
    return typeof v === "number";
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                key={c}
                className={sortKey === c ? "sorted" : ""}
                onClick={() => handleSort(c)}
              >
                {c}
                <span className="sort-icon">
                  {sortKey === c ? (sortDir === "asc" ? " ↑" : " ↓") : " ↕"}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c} className={isNum(row[c]) ? "num" : ""}>
                  {row[c] === null || row[c] === undefined
                    ? <span style={{ color: "var(--gray-300)" }}>null</span>
                    : String(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Pipeline trace ───────────────────────────────────────────────────────────

function PipelineTrace({ steps }: { steps: PipelineStep[] }) {
  const maxMs = Math.max(...steps.map((s) => s.latency_ms), 1);
  return (
    <div className="pipeline">
      {steps.map((step, i) => (
        <div key={i} className="pipeline-step">
          <div className={`step-dot ${step.status}`}>
            {STEP_LABELS[step.status] ? (
              <span style={{ fontSize: 7, letterSpacing: 0 }}>
                {step.status === "hit" ? "✓" : step.status === "ok" ? "✓" : step.status === "skip" ? "–" : step.status === "miss" ? "○" : "!"}
              </span>
            ) : null}
          </div>
          <div className="step-body">
            <div className="step-name">{step.name}</div>
            {step.detail && <div className="step-detail">{step.detail}</div>}
            <div className="step-timing">{step.latency_ms.toFixed(1)} ms</div>
            <div className="step-bar-bg">
              <div
                className="step-bar"
                style={{ width: `${(step.latency_ms / maxMs) * 100}%` }}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Technical details panel ──────────────────────────────────────────────────

function TechDetails({ sql, steps }: { sql: string; steps: PipelineStep[] }) {
  const [open, setOpen] = useState(false);
  const [techTab, setTechTab] = useState<"sql" | "trace">("sql");
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(sql).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  }

  return (
    <div className="tech-panel">
      <button
        className={`tech-toggle ${open ? "open" : ""}`}
        onClick={() => setOpen((v) => !v)}
      >
        Technical Details
        <span style={{ fontSize: 11, color: "var(--gray-400)", marginLeft: 8 }}>
          SQL · Pipeline trace · {steps.length} steps
        </span>
        <span className="chevron">▼</span>
      </button>
      {open && (
        <div className="tech-inner">
          <div className="tech-tabs">
            <button
              className={`tech-tab-btn ${techTab === "sql" ? "active" : ""}`}
              onClick={() => setTechTab("sql")}
            >
              Generated SQL
            </button>
            <button
              className={`tech-tab-btn ${techTab === "trace" ? "active" : ""}`}
              onClick={() => setTechTab("trace")}
            >
              Pipeline Trace
            </button>
          </div>
          {techTab === "sql" ? (
            <div className="sql-block">
              <button className="copy-btn" onClick={copy}>
                {copied ? "Copied!" : "Copy"}
              </button>
              <pre className="sql-code">{sql}</pre>
            </div>
          ) : (
            <PipelineTrace steps={steps} />
          )}
        </div>
      )}
    </div>
  );
}

// ─── Query Console tab ────────────────────────────────────────────────────────

function QueryConsole() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  async function submit(q: string) {
    const trimmed = q.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await runQuery(trimmed);
      setResult(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      submit(query);
    }
  }

  const eval_ = result?.evaluation;
  const matchColor =
    eval_?.match === "yes"
      ? "var(--success)"
      : eval_?.match === "partial"
      ? "var(--warning)"
      : "var(--danger)";

  return (
    <div>
      {/* ── Query input ── */}
      <div className="query-hero">
        <div className="query-hero-label">Natural Language Query</div>
        <div className="query-input-row">
          <textarea
            ref={taRef}
            className="query-textarea"
            rows={2}
            placeholder='Ask anything about your banking data — e.g. "Which branches have the most inactive accounts?"'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKey}
          />
          <button
            className="btn-analyze"
            disabled={loading || !query.trim()}
            onClick={() => submit(query)}
          >
            {loading ? "Analyzing…" : "Analyze"}
          </button>
        </div>
        <div className="example-row">
          {EXAMPLE_QUERIES.map((q) => (
            <span
              key={q}
              className="example-chip"
              onClick={() => {
                setQuery(q);
                taRef.current?.focus();
              }}
            >
              {q}
            </span>
          ))}
        </div>
      </div>

      {/* ── Loading state ── */}
      {loading && (
        <div className="card mb-24">
          <div className="card-body">
            <div style={{ fontSize: 12, color: "var(--gray-400)", marginBottom: 12 }}>
              Generating SQL and fetching results…
            </div>
            <Shimmer rows={5} />
          </div>
        </div>
      )}

      {/* ── Error state ── */}
      {error && !loading && (
        <div
          className="card mb-24"
          style={{ borderColor: "#fecaca", background: "var(--danger-bg)" }}
        >
          <div className="card-body" style={{ display: "flex", gap: 12 }}>
            <span style={{ fontSize: 18 }}>✗</span>
            <div>
              <div
                style={{ fontSize: 13, fontWeight: 600, color: "var(--danger)", marginBottom: 4 }}
              >
                Query Failed
              </div>
              <div style={{ fontSize: 13, color: "var(--gray-600)" }}>{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* ── Results ── */}
      {result && !loading && (
        <>
          {/* Executive summary */}
          {eval_?.executive_summary && (
            <div className="exec-banner mb-16">
              <span className="exec-banner-icon">💡</span>
              <div>
                <div className="exec-banner-label">Executive Summary</div>
                <div className="exec-banner-text">{eval_.executive_summary}</div>
              </div>
            </div>
          )}

          {/* Meta strip */}
          <div className="meta-strip">
            <ScoreChip score={eval_?.score ?? null} />
            {eval_?.match && eval_.match !== "unknown" && (
              <span className="meta-chip neutral">
                <span style={{ width: 8, height: 8, borderRadius: 2, background: matchColor, display: "inline-block" }} />
                Intent match: {eval_.match}
              </span>
            )}
            {result.source_tables.length > 0 && (
              <span className="meta-chip neutral">
                Tables: {result.source_tables.join(", ")}
              </span>
            )}
            <span className={`meta-chip ${result.from_cache ? "cached" : "uncached"}`}>
              {result.from_cache ? "⚡ Cached" : "⏱ Live query"}
            </span>
            <span className="meta-chip neutral">
              {result.row_count.toLocaleString()} rows · {result.execution_time_ms.toFixed(0)} ms
            </span>
          </div>

          {/* Chart suggestion */}
          {eval_?.chart_suggestion && (
            <div className="chart-suggestion">
              <span style={{ fontSize: 15 }}>
                {CHART_ICONS[eval_.chart_suggestion] ?? "◈"}
              </span>
              <span>
                Suggested visualisation: <strong>{eval_.chart_suggestion} chart</strong>
              </span>
            </div>
          )}

          {/* Data table */}
          <DataTable rows={result.rows} />

          {/* Proactive question */}
          {eval_?.proactive_question && (
            <div className="proactive-card">
              <span className="proactive-icon">💬</span>
              <div>
                <div className="proactive-label">Follow-up Question</div>
                <div className="proactive-text">{eval_.proactive_question}</div>
                <button
                  className="proactive-btn"
                  onClick={() => {
                    setQuery(eval_.proactive_question!);
                    window.scrollTo({ top: 0, behavior: "smooth" });
                    taRef.current?.focus();
                  }}
                >
                  Ask this
                </button>
              </div>
            </div>
          )}

          {/* Technical details */}
          <TechDetails sql={result.sql} steps={result.pipeline_steps} />
        </>
      )}

      {/* Empty state */}
      {!result && !loading && !error && (
        <div className="empty-state">
          <div className="empty-state-icon">⬡</div>
          <div className="empty-state-text">
            Ask a question above to explore your banking data
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Observability tab ────────────────────────────────────────────────────────

function ObservabilityTab() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(true);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
      .finally(() => setLoadingHealth(false));
  }, []);

  const services = health
    ? [
        { name: "API Server", ok: health.status === "ok", detail: "FastAPI / Python" },
        { name: "PostgreSQL", ok: health.database, detail: "psycopg3 async" },
        { name: "Redis Cache", ok: health.redis, detail: "Two-layer caching" },
        { name: "Ollama LLM", ok: health.ollama, detail: health.model ?? "—" },
      ]
    : [];

  const latencyRows = [
    { step: "NL Cache lookup", p50: "< 2 ms", p95: "< 5 ms", note: "Redis GET" },
    { step: "LLM SQL generation", p50: "~3 s", p95: "~8 s", note: "Ollama local inference" },
    { step: "SQL validation", p50: "< 1 ms", p95: "< 2 ms", note: "Regex safety check" },
    { step: "SQL Cache lookup", p50: "< 2 ms", p95: "< 5 ms", note: "Redis GET" },
    { step: "Database execution", p50: "~50 ms", p95: "~200 ms", note: "PostgreSQL + pgvector" },
    { step: "LLM evaluation", p50: "~2 s", p95: "~5 s", note: "Ollama (explain=true only)" },
  ];

  return (
    <div>
      <div className="section-title">Service Health</div>
      <div className="section-subtitle">
        Real-time status of each backend service component.
      </div>

      {loadingHealth ? (
        <Shimmer rows={3} />
      ) : health ? (
        <div className="service-grid mb-24">
          {services.map((s) => (
            <div key={s.name} className="service-card">
              <div className="service-card-label">{s.name}</div>
              <div className={`service-card-status ${s.ok ? "ok" : "err"}`}>
                {s.ok ? "Healthy" : "Offline"}
              </div>
              <div className="service-card-detail">{s.detail}</div>
            </div>
          ))}
        </div>
      ) : (
        <div
          className="card mb-24"
          style={{ borderColor: "#fecaca", background: "var(--danger-bg)", padding: "16px 20px" }}
        >
          <span style={{ fontSize: 13, color: "var(--danger)" }}>
            Could not reach backend — is the API server running on port 8000?
          </span>
        </div>
      )}

      <div className="section-title">Expected Latency per Pipeline Step</div>
      <div className="card mb-24">
        <table className="latency-table">
          <thead>
            <tr>
              <th>Step</th>
              <th>P50</th>
              <th>P95</th>
              <th className="latency-bar-cell"></th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {latencyRows.map((r, i) => (
              <tr key={i}>
                <td style={{ fontWeight: 500 }}>{r.step}</td>
                <td>{r.p50}</td>
                <td>{r.p95}</td>
                <td className="latency-bar-cell">
                  <div className="latency-bar-bg">
                    <div
                      className="latency-bar-fill"
                      style={{ width: `${[15, 90, 5, 15, 35, 65][i]}%` }}
                    />
                  </div>
                </td>
                <td style={{ color: "var(--gray-400)", fontSize: 12 }}>{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">Grafana Dashboard</div>
      <div className="section-subtitle">
        Full metrics, log panels, and latency trends are available in the Grafana
        observability stack (requires Docker).
      </div>
      <a href="http://localhost:3001" target="_blank" rel="noreferrer" className="grafana-link">
        <span>⎋</span>
        Open Grafana Dashboard
      </a>
    </div>
  );
}

// ─── Schema & Help tab ────────────────────────────────────────────────────────

function SchemaHelpTab() {
  const [schema, setSchema] = useState<SchemaTable[]>([]);
  const [openTable, setOpenTable] = useState<string | null>(null);

  useEffect(() => {
    fetchSchema().then(setSchema);
  }, []);

  const tips = [
    {
      icon: "🔍",
      title: "Ask naturally",
      text: 'Use plain English — "Show me top customers" or "How much did we earn last month?"',
    },
    {
      icon: "⚡",
      title: "Results are cached",
      text: "Repeated queries return instantly from Redis. Cache TTL is 5 minutes.",
    },
    {
      icon: "📊",
      title: "Check the chart hint",
      text: "The AI suggests bar, line, pie, or table — copy the data into your BI tool of choice.",
    },
    {
      icon: "🔗",
      title: "Follow-up questions",
      text: 'Click "Ask this" under any result to drill deeper with a single click.',
    },
  ];

  return (
    <div>
      <div className="section-title">Usage Tips</div>
      <div className="tips-grid mb-24">
        {tips.map((t) => (
          <div key={t.title} className="tip-card">
            <div className="tip-icon">{t.icon}</div>
            <div className="tip-title">{t.title}</div>
            <div className="tip-text">{t.text}</div>
          </div>
        ))}
      </div>

      <div className="section-title mb-8">Example Queries</div>
      <div className="example-query-grid mb-24">
        {[
          "Show me the top 5 branches by total deposits",
          "Which customers have more than 3 accounts?",
          "How many transactions failed in the last 7 days?",
          "What is the average balance for Premium accounts?",
          "Show transaction volume by type for this month",
          "List all frozen accounts with their customer names",
          "Which branch has the most business accounts?",
          "Total fees charged in the last 30 days",
        ].map((q) => (
          <div key={q} className="example-query-row">
            <span className="example-query-text">{q}</span>
            <span className="example-query-arrow">›</span>
          </div>
        ))}
      </div>

      <div className="section-title mb-8">Database Schema</div>
      <div className="schema-accordion">
        {schema.map((t) => (
          <div key={t.table_name}>
            <button
              className={`schema-table-btn ${openTable === t.table_name ? "open" : ""}`}
              onClick={() =>
                setOpenTable(openTable === t.table_name ? null : t.table_name)
              }
            >
              <span>{t.table_name}</span>
              <span style={{ fontSize: 12, color: "var(--gray-400)", fontWeight: 400 }}>
                {t.columns.length} columns {openTable === t.table_name ? "▲" : "▼"}
              </span>
            </button>
            {openTable === t.table_name && (
              <div className="schema-cols">
                {t.columns.map((c) => (
                  <div key={c.column_name} className="schema-col-row">
                    <span className="schema-col-name">
                      {c.column_name}
                      <span
                        style={{
                          marginLeft: 6,
                          fontSize: 10,
                          fontWeight: 400,
                          color: "var(--gray-400)",
                          fontFamily: "monospace",
                        }}
                      >
                        {c.data_type}
                      </span>
                    </span>
                    <span className="schema-col-desc">{c.description}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Architecture tab ─────────────────────────────────────────────────────────

function ArchitectureTab() {
  const components = [
    { name: "Next.js 13", role: "Frontend", detail: "Pages Router · TypeScript · SWR" },
    { name: "FastAPI", role: "API Layer", detail: "Python 3.10+ · asynccontextmanager lifespan" },
    { name: "Ollama (qwen:7b)", role: "LLM Inference", detail: "Local · no cloud API keys needed" },
    { name: "PostgreSQL + pgvector", role: "Primary Store", detail: "HNSW index · vector(384) · async psycopg3" },
    { name: "Redis", role: "Cache", detail: "NL query (5 min) · SQL result (5 min) · embeddings (24 h)" },
    { name: "OpenTelemetry", role: "Tracing", detail: "Custom JSONL exporter → Tempo" },
    { name: "Loki + Promtail", role: "Logging", detail: "Structured JSON log ingestion" },
    { name: "Grafana", role: "Dashboards", detail: "Pre-built 13-panel EchoSQL dashboard" },
  ];

  return (
    <div>
      {/* Executive section */}
      <div className="arch-section">
        <span className="arch-section-tag exec">For Everyone</span>
        <div className="arch-section-title">How EchoSQL Works</div>
        <div className="arch-section-intro">
          EchoSQL translates your plain-English questions into database queries using a
          locally-hosted AI model — no data ever leaves your environment. Results are
          delivered in seconds with automatic caching for instant repeat queries.
        </div>
        <div className="arch-value-grid">
          <div className="arch-value-card">
            <div className="arch-value-icon">🔒</div>
            <div className="arch-value-title">100% On-Premise</div>
            <div className="arch-value-text">
              All AI inference runs locally via Ollama. No data is sent to external APIs.
            </div>
          </div>
          <div className="arch-value-card">
            <div className="arch-value-icon">⚡</div>
            <div className="arch-value-title">Instant for Repeat Queries</div>
            <div className="arch-value-text">
              Redis caches every query. The second time you ask the same question, it
              returns in under 5 ms.
            </div>
          </div>
          <div className="arch-value-card">
            <div className="arch-value-icon">📈</div>
            <div className="arch-value-title">Full Observability</div>
            <div className="arch-value-text">
              Every query is traced end-to-end. Latency, cache rates, and errors are
              visible in the Grafana dashboard.
            </div>
          </div>
        </div>
        <div className="arch-flow">
          <div className="arch-flow-step">Your Question</div>
          <span className="arch-flow-arrow">→</span>
          <div className="arch-flow-step cache">Cache Check</div>
          <span className="arch-flow-arrow">→</span>
          <div className="arch-flow-step llm">AI Model</div>
          <span className="arch-flow-arrow">→</span>
          <div className="arch-flow-step db">Database</div>
          <span className="arch-flow-arrow">→</span>
          <div className="arch-flow-step">Results + Insights</div>
        </div>
      </div>

      {/* Technical section */}
      <div className="arch-section">
        <span className="arch-section-tag tech">Technical Detail</span>
        <div className="arch-section-title">System Components</div>
        <div className="arch-section-intro">
          EchoSQL is a single-host system built for local deployment. The 7-step
          pipeline adds observability, caching, and safety validation at every stage.
        </div>
        <table className="component-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Role</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {components.map((c) => (
              <tr key={c.name}>
                <td className="comp-name">{c.name}</td>
                <td>
                  <span className="tag">{c.role}</span>
                </td>
                <td style={{ color: "var(--gray-500)", fontSize: 12 }}>{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="arch-note">
          <span>ℹ</span>
          <span>
            The semantic-search layer uses <code>all-MiniLM-L6-v2</code> (384-dim
            vectors) via sentence-transformers. The HNSW index in pgvector makes
            embedding lookups sub-millisecond even at 100 k+ schema rows.
          </span>
        </div>
      </div>

      {/* Deep-dive section */}
      <div className="arch-section">
        <span className="arch-section-tag deep">Pipeline Deep-Dive</span>
        <div className="arch-section-title">The 7-Step Query Pipeline</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[
            ["1", "NL Cache Lookup", "MD5 hash of the normalised query is checked in Redis. A hit skips all remaining steps.", "< 5 ms"],
            ["2", "LLM SQL Generation", "Ollama runs qwen:7b-chat locally with a schema-aware system prompt to produce a SELECT statement.", "2–8 s"],
            ["3", "SQL Validation", "Regex check ensures only SELECT is present — no mutations, no DDL.", "< 1 ms"],
            ["4", "SQL Cache Lookup", "The generated SQL is hashed and checked in Redis before hitting the database.", "< 5 ms"],
            ["5", "Database Execution", "psycopg3 async executes the query against PostgreSQL. Large result sets are limited to 100 rows.", "10–200 ms"],
            ["6", "Cache Write", "Both the NL query result and the SQL result are written to Redis with a 5-minute TTL.", "< 5 ms"],
            ["7", "LLM Evaluation", "A second Ollama call scores SQL correctness and extracts business insight (explain=true only).", "1–5 s"],
          ].map(([num, name, desc, timing]) => (
            <div
              key={num}
              style={{
                display: "flex",
                gap: 14,
                padding: "12px 16px",
                background: "var(--gray-50)",
                borderRadius: "var(--radius)",
                border: "1px solid var(--border)",
              }}
            >
              <div
                style={{
                  width: 28, height: 28, borderRadius: "50%",
                  background: "var(--primary)", color: "#fff",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 12, fontWeight: 700, flexShrink: 0,
                }}
              >
                {num}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--gray-900)", marginBottom: 3 }}>
                  {name}
                </div>
                <div style={{ fontSize: 12, color: "var(--gray-500)", lineHeight: 1.5 }}>{desc}</div>
              </div>
              <div
                style={{
                  fontSize: 11, fontWeight: 600, color: "var(--gray-400)",
                  whiteSpace: "nowrap", alignSelf: "center",
                }}
              >
                {timing}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────

export default function Home() {
  const [tab, setTab] = useState<Tab>("Query Console");
  const [healthDots, setHealthDots] = useState<{
    api: boolean | null;
    db: boolean | null;
    ollama: boolean | null;
  }>({ api: null, db: null, ollama: null });

  useEffect(() => {
    fetchHealth()
      .then((h) =>
        setHealthDots({ api: h.status === "ok", db: h.database, ollama: h.ollama })
      )
      .catch(() => setHealthDots({ api: false, db: false, ollama: false }));
  }, []);

  function dotClass(v: boolean | null) {
    if (v === null) return "";
    return v ? "ok" : "err";
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-inner">
          <a href="/" className="logo">
            <div
              style={{
                width: 34, height: 34, borderRadius: 8,
                background: "linear-gradient(135deg,#3b82f6,#2563eb)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 16, fontWeight: 800, color: "#fff", letterSpacing: "-1px",
              }}
            >
              ES
            </div>
            <div className="logo-text">
              <span className="logo-name">EchoSQL</span>
              <span className="logo-tagline">Natural language. Instant intelligence.</span>
            </div>
          </a>
          <div className="health-dots">
            <div className="health-dot">
              <div className={`health-dot-circle ${dotClass(healthDots.api)}`} />
              API
            </div>
            <div className="health-dot">
              <div className={`health-dot-circle ${dotClass(healthDots.db)}`} />
              DB
            </div>
            <div className="health-dot">
              <div className={`health-dot-circle ${dotClass(healthDots.ollama)}`} />
              LLM
            </div>
          </div>
        </div>
      </header>

      {/* Tab bar */}
      <nav className="tabbar">
        <div className="tabbar-inner">
          {TABS.map((t) => (
            <button
              key={t}
              className={`tab-btn ${tab === t ? "active" : ""}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </nav>

      {/* Content */}
      <main className="content">
        {tab === "Query Console" && <QueryConsole />}
        {tab === "Observability" && <ObservabilityTab />}
        {tab === "Schema & Help" && <SchemaHelpTab />}
        {tab === "Architecture" && <ArchitectureTab />}
      </main>
    </div>
  );
}
