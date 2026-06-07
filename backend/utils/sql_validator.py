"""
SQL safety validation — allows only read-only SELECT queries.
"""

import re
from typing import Tuple

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DDL, DML

_BLOCKED: set = {
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE", "MERGE", "GRANT", "REVOKE", "EXECUTE", "EXEC", "CALL",
    "LOAD", "COPY", "VACUUM", "ANALYZE", "COMMENT",
}

MAX_LEN = 4_000


def validate_sql(sql: str) -> Tuple[bool, str]:
    """
    Return (True, "") when sql is a safe SELECT, otherwise (False, reason).

    Checks (in order):
      1. Non-empty
      2. Length cap
      3. Must begin with SELECT
      4. No DML/DDL keywords in the token stream
      5. No stacked statements (bare semicolons inside the query)
    """
    if not sql or not sql.strip():
        return False, "SQL query is empty"

    sql = sql.strip()

    if len(sql) > MAX_LEN:
        return False, f"SQL exceeds maximum allowed length ({MAX_LEN} chars)"

    upper = sql.upper().lstrip()
    if not upper.startswith("SELECT"):
        return False, "Only SELECT queries are allowed"

    # Parse and inspect every token
    try:
        statements = sqlparse.parse(sql)
        for stmt in statements:
            for token in stmt.flatten():
                tv = token.value.upper()
                if tv in _BLOCKED:
                    return False, f"Keyword '{token.value}' is not permitted"
    except Exception:
        # Fallback: naive regex scan
        for word in re.split(r"[\s;,()=\[\]]+", upper):
            if word in _BLOCKED:
                return False, f"Keyword '{word}' is not permitted"

    # Block stacked queries: strip string literals then look for semicolons
    stripped = re.sub(r"'[^']*'", "''", sql)
    stripped = re.sub(r'"[^"]*"', '""', stripped)
    if ";" in stripped.rstrip(";"):
        return False, "Multiple SQL statements are not allowed"

    return True, ""
