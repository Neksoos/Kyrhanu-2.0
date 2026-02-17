from __future__ import annotations

from sqlalchemy import text
from app.core.db import engine


MARKER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_bootstrap (
  id TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

BOOTSTRAP_ID = "001_users_sql"


async def ensure_schema() -> None:
    """
    Runs app/db/001_users.sql once (on a clean DB).
    Uses schema_bootstrap table as a marker.
    """
    sql_path = "app/db/001_users.sql"

    async with engine.begin() as conn:
        await conn.execute(text(MARKER_TABLE_SQL))

        already = await conn.execute(
            text("SELECT 1 FROM schema_bootstrap WHERE id = :id"),
            {"id": BOOTSTRAP_ID},
        )
        if already.first():
            return

        # read SQL file from container FS
        with open(sql_path, "r", encoding="utf-8") as f:
            sql_text = f.read()

        # Execute as a whole script
        # (Postgres driver can handle multiple statements separated by ';' here)
        # If your platform refuses multi-statement, tell me — I'll change to a safe splitter.
        await conn.execute(text(sql_text))

        await conn.execute(
            text("INSERT INTO schema_bootstrap (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
            {"id": BOOTSTRAP_ID},
        )