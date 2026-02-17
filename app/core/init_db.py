# app/core/init_db.py
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


def _split_sql(script: str) -> list[str]:
    """
    Split SQL script by ';' but NOT inside single/double quotes.
    Also strips out -- line comments.
    Good enough for simple schema .sql (CREATE TABLE, INSERT, etc).
    """
    lines = []
    for line in script.splitlines():
        # remove -- comments
        if "--" in line:
            line = line.split("--", 1)[0]
        lines.append(line)
    s = "\n".join(lines)

    statements: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False

    i = 0
    while i < len(s):
        ch = s[i]

        if ch == "'" and not in_double:
            # handle escaped '' inside strings
            if in_single and i + 1 < len(s) and s[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)

    return statements


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

        with open(sql_path, "r", encoding="utf-8") as f:
            sql_text = f.read()

        statements = _split_sql(sql_text)
        for stmt in statements:
            await conn.execute(text(stmt))

        await conn.execute(
            text("INSERT INTO schema_bootstrap (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
            {"id": BOOTSTRAP_ID},
        )