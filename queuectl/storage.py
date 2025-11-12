import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

DB_PATH = Path.home() / ".queuectl" / "queue.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()  # SQLite isn't fully thread-safe without guarding connections


def get_connection():
    """Return a new SQLite connection with WAL enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Jobs table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            state TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            run_after REAL DEFAULT 0,     -- timestamp when next retry is allowed
            lease_id TEXT DEFAULT NULL,   -- worker that claimed this job
            lease_until REAL DEFAULT NULL -- timestamp when lock expires
        );
    """
    )

    # DLQ table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dlq (
            id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            reason TEXT NOT NULL,
            failed_at TEXT NOT NULL
        );
    """
    )

    # Config table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """
    )

    conn.commit()
    conn.close()


def execute(query: str, params: Iterable[Any] = ()):
    """Thread-safe execute for write operations."""
    with _lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        conn.close()


def fetchone(query: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    with _lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        conn.close()
        return row


def fetchall(query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with _lock:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        return rows
