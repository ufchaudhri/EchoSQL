"""
Schema endpoint — returns the database schema grouped by table.
"""

import logging
from fastapi import APIRouter

from services.db_service import get_schema_info

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/schema")
async def get_schema():
    """Return database schema metadata grouped by table name."""
    rows = await get_schema_info()

    tables: dict = {}
    for row in rows:
        t = row["table_name"]
        if t not in tables:
            tables[t] = {"name": t, "columns": []}
        tables[t]["columns"].append(
            {"column": row["column_name"], "description": row["description"]}
        )

    return {"tables": list(tables.values()), "table_count": len(tables)}
