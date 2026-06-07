"""
Database service — async PostgreSQL query execution via psycopg3.
"""

import logging
from typing import Any, Dict, List

import psycopg
from psycopg.rows import dict_row

from config import DATABASE_URL

logger = logging.getLogger(__name__)


async def execute_query(sql: str) -> List[Dict[str, Any]]:
    """
    Execute a SQL SELECT and return rows as a list of plain dicts.

    Raises ValueError with a user-facing message on database errors.
    """
    try:
        aconn = await psycopg.AsyncConnection.connect(DATABASE_URL, row_factory=dict_row)
        async with aconn:
            async with aconn.cursor() as cur:
                await cur.execute(sql)
                rows = await cur.fetchall()
                return [dict(r) for r in rows]
    except psycopg.Error as e:
        msg = str(e).split("\n")[0]  # first line is the human-readable message
        logger.error("psycopg error: %s", e)
        raise ValueError(f"Database error: {msg}")
    except Exception as e:
        logger.error("Unexpected DB error: %s", e)
        raise ValueError(f"Query failed: {e}")


async def get_schema_info() -> List[Dict[str, Any]]:
    """Return all rows from schema_context, ordered by table then column."""
    try:
        return await execute_query(
            "SELECT table_name, column_name, description "
            "FROM schema_context ORDER BY table_name, column_name"
        )
    except Exception as e:
        logger.error("Failed to fetch schema info: %s", e)
        return []


async def check_db_health() -> bool:
    """Return True if the database connection is reachable."""
    try:
        aconn = await psycopg.AsyncConnection.connect(DATABASE_URL)
        async with aconn:
            async with aconn.cursor() as cur:
                await cur.execute("SELECT 1")
        return True
    except Exception:
        return False
