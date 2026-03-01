"""
VoltLegal — Database Module
Persistent storage via Turso (libSQL) cloud or local SQLite fallback.
All functions are async to support both backends.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN")
DB_PATH = os.getenv("DB_PATH", "voltlegal.db")

logger = logging.getLogger(__name__)

_use_turso = bool(TURSO_URL and TURSO_TOKEN)

if _use_turso:
    import libsql_client


# ─── Connection Helpers ──────────────────────────────────────────────────────

def _get_sqlite_conn():
    """Get a local SQLite connection with WAL mode and dict rows."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _new_turso_client():
    """Create a new Turso async client (use with 'async with')."""
    return libsql_client.create_client(url=TURSO_URL, auth_token=TURSO_TOKEN)


def _rs_to_dicts(rs) -> list[dict]:
    """Convert a libsql_client ResultSet to a list of dicts."""
    if not rs.rows:
        return []
    return [dict(zip(rs.columns, row)) for row in rs.rows]


def _rs_first(rs) -> dict | None:
    """Get first row of a ResultSet as dict, or None."""
    if not rs.rows:
        return None
    return dict(zip(rs.columns, rs.rows[0]))


# ─── Schema ──────────────────────────────────────────────────────────────────

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        telegram_id   INTEGER PRIMARY KEY,
        first_name    TEXT,
        last_name     TEXT,
        username      TEXT,
        joined_at     TEXT DEFAULT (datetime('now')),
        last_active   TEXT DEFAULT (datetime('now')),
        total_queries INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS conversations (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id   INTEGER NOT NULL,
        conv_type     TEXT NOT NULL,
        user_message  TEXT,
        bot_response  TEXT,
        created_at    TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id   INTEGER NOT NULL,
        session_type  TEXT NOT NULL,
        history_json  TEXT,
        summary       TEXT,
        created_at    TEXT DEFAULT (datetime('now')),
        updated_at    TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
    )""",
    """CREATE TABLE IF NOT EXISTS feedback (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id   INTEGER NOT NULL,
        username      TEXT,
        message       TEXT,
        created_at    TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(telegram_id)",
    "CREATE INDEX IF NOT EXISTS idx_conv_time ON conversations(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(telegram_id, session_type)",
]


async def init_db():
    """Create all tables if they don't exist. Safe to call every startup."""
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                await client.batch(_SCHEMA)
            logger.info("Database initialized (Turso)")
        else:
            conn = _get_sqlite_conn()
            try:
                for stmt in _SCHEMA:
                    conn.execute(stmt)
                conn.commit()
            finally:
                conn.close()
            logger.info(f"Database initialized at {DB_PATH}")
    except Exception as e:
        logger.error(f"Database init error: {e}")


# ─── User Functions ──────────────────────────────────────────────────────────

async def upsert_user(telegram_id: int, first_name: str = None,
                      last_name: str = None, username: str = None):
    """Insert or update a user record."""
    sql = """
        INSERT INTO users (telegram_id, first_name, last_name, username)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            first_name  = COALESCE(excluded.first_name, first_name),
            last_name   = COALESCE(excluded.last_name, last_name),
            username    = COALESCE(excluded.username, username),
            last_active = datetime('now')
    """
    params = [telegram_id, first_name, last_name, username]
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                await client.execute(sql, params)
        else:
            conn = _get_sqlite_conn()
            try:
                conn.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"upsert_user error: {e}")


async def increment_query_count(telegram_id: int):
    """Increment total_queries by 1 for a user."""
    sql = """
        UPDATE users SET total_queries = total_queries + 1,
                         last_active = datetime('now')
        WHERE telegram_id = ?
    """
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                await client.execute(sql, [telegram_id])
        else:
            conn = _get_sqlite_conn()
            try:
                conn.execute(sql, (telegram_id,))
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"increment_query_count error: {e}")


async def get_user(telegram_id: int) -> dict | None:
    """Return a user dict or None."""
    sql = "SELECT * FROM users WHERE telegram_id = ?"
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                rs = await client.execute(sql, [telegram_id])
                return _rs_first(rs)
        else:
            conn = _get_sqlite_conn()
            try:
                row = conn.execute(sql, (telegram_id,)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"get_user error: {e}")
        return None


# ─── Conversation Functions ──────────────────────────────────────────────────

async def log_conversation(telegram_id: int, conv_type: str,
                           user_message: str, bot_response: str):
    """Save a message pair to conversations table."""
    sql = """
        INSERT INTO conversations (telegram_id, conv_type, user_message, bot_response)
        VALUES (?, ?, ?, ?)
    """
    params = [telegram_id, conv_type, user_message, bot_response]
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                await client.execute(sql, params)
        else:
            conn = _get_sqlite_conn()
            try:
                conn.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"log_conversation error: {e}")


async def get_user_history(telegram_id: int, limit: int = 10) -> list[dict]:
    """Return last N conversations for a user, newest first."""
    sql = """
        SELECT conv_type, user_message, bot_response, created_at
        FROM conversations
        WHERE telegram_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                rs = await client.execute(sql, [telegram_id, limit])
                return _rs_to_dicts(rs)
        else:
            conn = _get_sqlite_conn()
            try:
                rows = conn.execute(sql, (telegram_id, limit)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"get_user_history error: {e}")
        return []


# ─── Session Functions ───────────────────────────────────────────────────────

async def save_session(telegram_id: int, session_type: str,
                       history_json: str, summary: str):
    """Save an active session with full history JSON."""
    sql = """
        INSERT INTO sessions (telegram_id, session_type, history_json, summary)
        VALUES (?, ?, ?, ?)
    """
    params = [telegram_id, session_type, history_json, summary]
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                await client.execute(sql, params)
        else:
            conn = _get_sqlite_conn()
            try:
                conn.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"save_session error: {e}")


async def get_last_session(telegram_id: int, session_type: str) -> dict | None:
    """Return the most recent session of a given type for a user."""
    sql = """
        SELECT * FROM sessions
        WHERE telegram_id = ? AND session_type = ?
        ORDER BY updated_at DESC
        LIMIT 1
    """
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                rs = await client.execute(sql, [telegram_id, session_type])
                return _rs_first(rs)
        else:
            conn = _get_sqlite_conn()
            try:
                row = conn.execute(sql, (telegram_id, session_type)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"get_last_session error: {e}")
        return None


# ─── Feedback Functions ──────────────────────────────────────────────────────

async def save_feedback(telegram_id: int, username: str, message: str):
    """Store user feedback."""
    sql = """
        INSERT INTO feedback (telegram_id, username, message)
        VALUES (?, ?, ?)
    """
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                await client.execute(sql, [telegram_id, username, message])
        else:
            conn = _get_sqlite_conn()
            try:
                conn.execute(sql, (telegram_id, username, message))
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"save_feedback error: {e}")


async def get_all_feedback() -> list[dict]:
    """Return all feedback rows (admin use)."""
    sql = "SELECT * FROM feedback ORDER BY created_at DESC"
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                rs = await client.execute(sql)
                return _rs_to_dicts(rs)
        else:
            conn = _get_sqlite_conn()
            try:
                rows = conn.execute(sql).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"get_all_feedback error: {e}")
        return []


# ─── Maintenance ─────────────────────────────────────────────────────────────

async def cleanup_old_conversations(days: int = 30):
    """Delete conversations older than N days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    sql = "DELETE FROM conversations WHERE created_at < ?"
    try:
        if _use_turso:
            async with _new_turso_client() as client:
                rs = await client.execute(sql, [cutoff])
                deleted = rs.rows_affected
        else:
            conn = _get_sqlite_conn()
            try:
                result = conn.execute(sql, (cutoff,))
                deleted = result.rowcount
                conn.commit()
            finally:
                conn.close()
        logger.info(f"Cleaned up {deleted} conversations older than {days} days")
        return deleted
    except Exception as e:
        logger.error(f"cleanup_old_conversations error: {e}")
        return 0
