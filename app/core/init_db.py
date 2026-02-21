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

# IMPORTANT: paths are relative to repo root
SCRIPTS: list[tuple[str, str]] = [
    ("001_users_sql", "app/db/001_users.sql"),
    ("002_seed_sql", "app/db/002_seed.sql"),
]

# One global lock id for schema bootstrap (any int64 is fine)
BOOTSTRAP_LOCK_ID = 924173

# Common Postgres SQLSTATE codes we can safely ignore for idempotent bootstrap
# 42P07 duplicate_table, 42710 duplicate_object, 42701 duplicate_column,
# 42P06 duplicate_schema, 23505 unique_violation
IGNORABLE_SQLSTATES = {"42P07", "42710", "42701", "42P06", "23505"}


def _repo_root() -> Path:
    # .../repo/app/core/init_db.py -> parents[2] == repo
    return Path(__file__).resolve().parents[2]


def _split_sql(script: str) -> list[str]:
    """
    Split SQL script by ';' but NOT inside single/double quotes.
    Also strips out -- line comments (simple).
    Good enough for simple schema .sql (CREATE TABLE, INSERT, etc).
    """
    lines = []
    for line in script.splitlines():
        # remove -- comments (naive)
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


def _sqlstate(exc: Exception) -> str | None:
    # asyncpg exceptions often have .sqlstate; SQLAlchemy wraps in DBAPIError with .orig
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
    # fallback string checks (covers some wrapped messages)
    if "already exists" in msg:
        return True
    if "duplicate key value violates unique constraint" in msg:
        return True
    return False


async def ensure_schema() -> None:
    """
    Runs schema SQL scripts once.
    Uses schema_bootstrap table as a marker.

    Protection:
      - pg_advisory_xact_lock to prevent concurrent bootstrap on multi-instance deploys
      - ignores harmless duplicate DDL / duplicate inserts if DB already has objects
    """
    repo = _repo_root()

    async with engine.begin() as conn:
        # Create marker table first
        await conn.execute(text(MARKER_TABLE_SQL))

        # ✅ Prevent concurrent startup races (Railway multi-instances)
        await conn.exec_driver_sql(f"SELECT pg_advisory_xact_lock({BOOTSTRAP_LOCK_ID});")

        for script_id, rel_path in SCRIPTS:
            # Re-check marker after lock (important on multi-instance)
            already = await conn.execute(
                text("SELECT 1 FROM schema_bootstrap WHERE id = :id"),
                {"id": script_id},
            )
            if already.first():
                continue

            sql_file = repo / rel_path
            if not sql_file.exists():
                # Optional scripts (e.g., seeds) may be absent in some deployments.
                continue

            sql_text = sql_file.read_text(encoding="utf-8")
            statements = _split_sql(sql_text)

            for stmt in statements:
                if not stmt.strip():
                    continue
                try:
                    # Use exec_driver_sql to avoid SQLAlchemy bind-param parsing (':' in JSON, etc.)
                    await conn.exec_driver_sql(stmt)
                except Exception as e:
                    # If DB is already partially/fully bootstrapped, ignore harmless duplicates
                    if _is_ignorable(e):
                        continue
                    # If it's SQLAlchemy wrapper, include orig for easier logs
                    if isinstance(e, DBAPIError) and e.orig:
                        raise e.orig
                    raise

            # Mark script as applied
            await conn.execute(
                text(
                    "INSERT INTO schema_bootstrap (id) VALUES (:id) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": script_id},
            )
