const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface PipelineStep {
  name: string;
  status: "hit" | "miss" | "ok" | "skip" | "error";
  latency_ms: number;
  detail: string;
}

export interface Evaluation {
  score: number | null;
  match: "yes" | "partial" | "no" | "unknown";
  explanation: string;
  executive_summary?: string;
  chart_suggestion?: "bar" | "line" | "pie" | "table";
  proactive_question?: string;
}

export interface QueryResult {
  sql: string;
  rows: Record<string, unknown>[];
  row_count: number;
  execution_time_ms: number;
  from_cache: boolean;
  source_tables: string[];
  pipeline_steps: PipelineStep[];
  evaluation?: Evaluation;
}

export interface HealthStatus {
  status: string;
  database: boolean;
  redis: boolean;
  ollama: boolean;
  model: string;
}

export interface SchemaColumn {
  column_name: string;
  data_type: string;
  description?: string;
}

export interface SchemaTable {
  table_name: string;
  columns: SchemaColumn[];
}

export async function runQuery(query: string): Promise<QueryResult> {
  const res = await fetch(`${BASE}/api/query?explain=true`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

export async function fetchSchema(): Promise<SchemaTable[]> {
  const res = await fetch(`${BASE}/api/schema`).catch(() => null);
  if (!res || !res.ok) return STATIC_SCHEMA;
  return res.json().catch(() => STATIC_SCHEMA);
}

export const fetcher = (url: string) =>
  fetch(BASE + url).then((r) => r.json());

// Static fallback — always shown if /api/schema endpoint is not available
const STATIC_SCHEMA: SchemaTable[] = [
  {
    table_name: "customers",
    columns: [
      { column_name: "customer_id", data_type: "integer", description: "Primary key" },
      { column_name: "name", data_type: "text", description: "Full name" },
      { column_name: "email", data_type: "text", description: "Unique email address" },
      { column_name: "phone", data_type: "text", description: "Contact number" },
      { column_name: "account_type", data_type: "text", description: "Savings | Checking | Premium | Business" },
      { column_name: "kyc_status", data_type: "text", description: "Verified | Pending | Rejected" },
      { column_name: "created_at", data_type: "timestamp", description: "Registration timestamp" },
    ],
  },
  {
    table_name: "accounts",
    columns: [
      { column_name: "account_id", data_type: "integer", description: "Primary key" },
      { column_name: "customer_id", data_type: "integer", description: "FK → customers" },
      { column_name: "branch_id", data_type: "integer", description: "FK → branches" },
      { column_name: "account_number", data_type: "text", description: "Unique 20-char identifier" },
      { column_name: "account_type", data_type: "text", description: "Savings | Checking | Premium | Business" },
      { column_name: "balance", data_type: "decimal", description: "Current balance" },
      { column_name: "status", data_type: "text", description: "Active | Inactive | Frozen" },
      { column_name: "created_at", data_type: "timestamp", description: "Account creation date" },
    ],
  },
  {
    table_name: "transactions",
    columns: [
      { column_name: "transaction_id", data_type: "integer", description: "Primary key" },
      { column_name: "account_id", data_type: "integer", description: "FK → accounts" },
      { column_name: "transaction_type_id", data_type: "integer", description: "FK → transaction_types" },
      { column_name: "amount", data_type: "decimal", description: "Transaction value" },
      { column_name: "balance_after", data_type: "decimal", description: "Account balance post-transaction" },
      { column_name: "description", data_type: "text", description: "Free-text note" },
      { column_name: "status", data_type: "text", description: "Completed | Pending | Failed" },
      { column_name: "transaction_date", data_type: "date", description: "Calendar date of the transaction" },
    ],
  },
  {
    table_name: "branches",
    columns: [
      { column_name: "branch_id", data_type: "integer", description: "Primary key" },
      { column_name: "branch_code", data_type: "text", description: "Short code e.g. NYC-001" },
      { column_name: "location", data_type: "text", description: "Street address" },
      { column_name: "city", data_type: "text", description: "City name" },
      { column_name: "state", data_type: "text", description: "State or region" },
      { column_name: "manager_name", data_type: "text", description: "Branch manager full name" },
    ],
  },
  {
    table_name: "transaction_types",
    columns: [
      { column_name: "type_id", data_type: "integer", description: "Primary key" },
      { column_name: "type_name", data_type: "text", description: "e.g. Deposit, ATM Withdrawal, Wire Transfer" },
      { column_name: "category", data_type: "text", description: "Deposit | Withdrawal | Transfer | Fee | Interest" },
    ],
  },
];
