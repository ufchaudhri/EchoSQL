"""
LLM service for SQL generation using Ollama.
"""

import re
import logging
from typing import Optional

import httpx
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from config import OLLAMA_HOST, OLLAMA_MODEL

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

SCHEMA_PROMPT = """You are a PostgreSQL expert. Convert natural-language questions to a single SQL SELECT query.

Database schema (banking domain):

  customers(customer_id PK, name, email, phone,
            account_type IN ('Savings','Checking','Premium','Business'),
            kyc_status   IN ('Verified','Pending','Rejected'),
            created_at)

  branches(branch_id PK, branch_code, location, city, state, country, manager_name, created_at)

  accounts(account_id PK, customer_id FK→customers, branch_id FK→branches,
           account_number, account_type IN ('Savings','Checking','Premium','Business'),
           balance DECIMAL, status IN ('Active','Inactive','Frozen'), created_at)

  transaction_types(type_id PK, type_name, description,
                    category IN ('Deposit','Withdrawal','Transfer','Fee','Interest'))
  -- type_name values: Deposit, Withdrawal, Transfer Out, Transfer In, ATM Withdrawal,
  --   Online Transfer, Salary Deposit, Bill Payment, Interest,
  --   Maintenance Fee, Overdraft Fee, ATM Fee, Wire Transfer, Check Deposit, Refund

  transactions(transaction_id PK, account_id FK→accounts,
               transaction_type_id FK→transaction_types,
               amount DECIMAL, balance_after DECIMAL, description,
               status IN ('Completed','Pending','Failed'),
               created_at TIMESTAMP, transaction_date DATE)

Pre-built views (use when relevant):
  customer_account_summary(customer_id, name, email, num_accounts, total_balance, avg_balance, created_at)
  transaction_summary_by_type(type_name, category, transaction_count, total_amount, avg_amount, first_transaction, last_transaction)
  branch_performance(branch_id, branch_code, location, city, num_accounts, num_customers, total_deposits, avg_account_balance)

Rules:
  1. Output ONLY the raw SQL — no markdown, no explanation, no trailing semicolon.
  2. Always add LIMIT 100 unless the question asks for totals/aggregates.
  3. Use table aliases.
  4. Use explicit JOIN syntax.
"""


async def generate_sql(user_query: str) -> Optional[str]:
    """
    Generate a SQL SELECT statement from a natural-language query via Ollama.
    Returns the SQL string on success, None on failure.
    """
    prompt = f"{SCHEMA_PROMPT}\n\nQuestion: {user_query}\n\nSQL:"

    with tracer.start_as_current_span("ollama.http.generate") as span:
        span.set_attribute("llm.model", OLLAMA_MODEL)
        span.set_attribute("llm.prompt_chars", len(prompt))
        span.set_attribute("http.url", f"{OLLAMA_HOST}/api/generate")

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 512,
                            "stop": ["\n\n", "Question:", "/*"],
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()

                span.set_attribute("llm.tokens_generated", data.get("eval_count", 0))
                span.set_attribute("llm.eval_duration_ms",
                                   round(data.get("eval_duration", 0) / 1e6, 2))
                span.set_attribute("llm.total_duration_ms",
                                   round(data.get("total_duration", 0) / 1e6, 2))
                span.set_attribute("llm.load_duration_ms",
                                   round(data.get("load_duration", 0) / 1e6, 2))

                raw = data.get("response", "").strip()
                sql = _extract_sql(raw)
                span.set_attribute("llm.sql_extracted", sql is not None)
                if sql:
                    span.set_attribute("llm.sql_preview", sql[:200])
                return sql

        except httpx.TimeoutException:
            span.set_status(StatusCode.ERROR, "timeout")
            logger.error("Ollama request timed out after 90 s",
                         extra={"event": "llm.timeout", "host": OLLAMA_HOST})
            return None
        except httpx.ConnectError:
            span.set_status(StatusCode.ERROR, "connect_error")
            logger.error("Cannot connect to Ollama at %s — is `ollama serve` running?",
                         OLLAMA_HOST, extra={"event": "llm.connect_error", "host": OLLAMA_HOST})
            return None
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            logger.error("LLM generation error: %s", e, extra={"event": "llm.error"})
            return None


def _extract_sql(raw: str) -> Optional[str]:
    """Pull a clean SELECT statement from the raw LLM output."""
    if not raw:
        return None
    raw = re.sub(r"```sql\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```\s*", "", raw)
    raw = raw.strip()
    match = re.search(r"(SELECT\b.+)", raw, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip().rstrip(";").strip()
    if raw.upper().startswith("SELECT"):
        return raw.rstrip(";").strip()
    return None


async def explain_sql(nl_query: str, sql: str) -> dict:
    """
    Ask the LLM to evaluate the generated SQL and produce executive insights.

    Returns a dict with:
      score               int   0-100 confidence the SQL is correct
      match               str   "yes" | "partial" | "no"
      explanation         str   one sentence describing what the query does
      executive_summary   str   1-2 sentence business insight from the data
      chart_suggestion    str   "bar" | "line" | "pie" | "table"
      proactive_question  str   one follow-up question for the user
    """
    prompt = (
        f'A user asked: "{nl_query}"\n\n'
        f"The system generated this SQL:\n{sql}\n\n"
        "Evaluate the SQL and provide executive insights.\n"
        "Reply in EXACTLY this format (no other text):\n"
        "SCORE: <0-100>\n"
        "MATCH: <yes|partial|no>\n"
        "EXPLANATION: <one sentence starting with 'This query'>\n"
        "SUMMARY: <1-2 sentences of business insight — what does this data reveal?>\n"
        "CHART: <bar|line|pie|table>\n"
        "QUESTION: <one proactive follow-up question the user might ask next>"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 200},
                },
            )
            response.raise_for_status()
            raw = response.json().get("response", "").strip()
            return _parse_eval(raw)
    except Exception as e:
        logger.warning("explain_sql failed: %s", e)
        return {
            "score": None, "match": "unknown",
            "explanation": "Evaluation unavailable.",
            "executive_summary": None,
            "chart_suggestion": None,
            "proactive_question": None,
        }


def _parse_eval(raw: str) -> dict:
    score_m   = re.search(r"SCORE:\s*(\d+)", raw)
    match_m   = re.search(r"MATCH:\s*(yes|partial|no)", raw, re.IGNORECASE)
    expl_m    = re.search(r"EXPLANATION:\s*(.+?)(?=\n[A-Z]+:|$)", raw, re.IGNORECASE | re.DOTALL)
    summary_m = re.search(r"SUMMARY:\s*(.+?)(?=\n[A-Z]+:|$)", raw, re.IGNORECASE | re.DOTALL)
    chart_m   = re.search(r"CHART:\s*(bar|line|pie|table)", raw, re.IGNORECASE)
    question_m = re.search(r"QUESTION:\s*(.+?)(?=\n[A-Z]+:|$)", raw, re.IGNORECASE | re.DOTALL)
    return {
        "score":              int(score_m.group(1)) if score_m else None,
        "match":              match_m.group(1).lower() if match_m else "unknown",
        "explanation":        expl_m.group(1).strip() if expl_m else raw[:200],
        "executive_summary":  summary_m.group(1).strip() if summary_m else None,
        "chart_suggestion":   chart_m.group(1).lower() if chart_m else None,
        "proactive_question": question_m.group(1).strip() if question_m else None,
    }


async def check_ollama_health() -> bool:
    """Return True if Ollama is reachable and the configured model is available."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            if resp.status_code == 200:
                names = [m.get("name", "") for m in resp.json().get("models", [])]
                return any(OLLAMA_MODEL in n for n in names)
    except Exception:
        pass
    return False
