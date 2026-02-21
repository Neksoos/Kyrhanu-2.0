# app/core/init_db.py
from __future__ import annotations

from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import engine


MARKER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_bootstrap (
  id TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

SCRIPTS: list[tuple[str, str]] = [
    ("001_users_sql", "app/db/001_users.sql"),
    ("002_seed_sql", "app/db/002_seed.sql"),
]

BOOTSTRAP_LOCK_ID = 924173

# Postgres SQLSTATE we can safely ignore *inside a savepoint*
IGNORABLE_SQLSTATES = {
    "42P07",  # duplicate_table
    "42710",  # duplicate_object
    "42701",  # duplicate_column
    "42P06",  # duplicate_schema
    "23505",  # unique_violation
}


def _repo_root() -> Path:
    # Works both for /app/app/core/init_db.py and ./app/core/init_db.py
    p = Path(__file__).resolve()
    # try: .../app/core/init_db.py -> parents[2] == repo root
    # try: .../app/app/core/init_db.py -> parents[2] == /app (repo root)
    return p.parents[2]


def _split_sql(script: str) -> list[str]:
    """
    Split SQL script by ';' but NOT inside single/double quotes.
    Also strips out -- line comments.
    Good enough for simple schema .sql (CREATE TABLE, INSERT, etc).
    """
    lines = []
    for line in script.splitlines():
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


def _sqlstate(exc: Exception) -> str | None:
    for obj in (exc, getattr(exc, "orig", None)):
        if not obj:
            continue
        val = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if val:
            return str(val)
    return None


def _is_ignorable(exc: Exception) -> bool:
    state = _sqlstate(exc)
    if state in IGNORABLE_SQLSTATES:
        return True

    msg = str(exc).lower()
    if "already exists" in msg:
        return True
    if "duplicate key value violates unique constraint" in msg:
        return True
    return False


async def ensure_schema() -> None:
    """
    Runs schema SQL scripts once.
    Uses schema_bootstrap table as a marker.

    IMPORTANT:
    - Any SQL error aborts a Postgres transaction.
    - Therefore every statement runs in a SAVEPOINT (nested tx).
      If statement fails with ignorable "already exists"/duplicate — rollback savepoint and continue.
    """
    repo = _repo_root()

    async with engine.begin() as conn:
        await conn.execute(text(MARKER_TABLE_SQL))

        # Prevent concurrent bootstrap between multiple Railway instances
        await conn.exec_driver_sql(f"SELECT pg_advisory_xact_lock({BOOTSTRAP_LOCK_ID});")

        for script_id, rel_path in SCRIPTS:
            already = await conn.execute(
                text("SELECT 1 FROM schema_bootstrap WHERE id = :id"),
                {"id": script_id},
            )
            if already.first():
                continue

            sql_file = repo / rel_path
            if not sql_file.exists():
                continue

            sql_text = sql_file.read_text(encoding="utf-8")
            statements = _split_sql(sql_text)

            for stmt in statements:
                stmt = stmt.strip()
                if not stmt:
                    continue

                try:
                    # ✅ SAVEPOINT per statement so one failure doesn't abort the whole transaction
                    async with conn.begin_nested():
                        await conn.exec_driver_sql(stmt)
                except Exception as e:
                    # unwrap DBAPIError if present
                    inner = e.orig if isinstance(e, DBAPIError) and getattr(e, "orig", None) else e

                    if _is_ignorable(inner):
                        # ignorable errors are safe now because begin_nested() rolled back
                        continue

                    # real error -> fail startup with clear root cause
                    raise inner

            await conn.execute(
                text(
                    "INSERT INTO schema_bootstrap (id) VALUES (:id) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": script_id},
            )
