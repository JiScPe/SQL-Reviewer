import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("events.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deploy_date TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'Queued',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                step TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posted_issues (
                issue_id_hash TEXT PRIMARY KEY,
                run_id INTEGER NOT NULL,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_posted_issues_run_id ON posted_issues(run_id)
        """)


def create_run(deploy_date: str) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO runs (deploy_date, state) VALUES (?, 'Queued')",
            (deploy_date,)
        )
        return cursor.lastrowid


def update_run_state(run_id: int, state: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE runs SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (state, run_id)
        )


def add_event(run_id: int, step: str, status: str, message: str = None):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO events (run_id, step, status, message) VALUES (?, ?, ?, ?)",
            (run_id, step, status, message)
        )


def get_events(run_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY timestamp",
            (run_id,)
        ).fetchall()


def get_run(run_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()


def issue_posted(issue_id_hash: str, run_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM posted_issues WHERE issue_id_hash = ? AND run_id = ?",
            (issue_id_hash, run_id)
        ).fetchone()
        return row is not None


def mark_issue_posted(issue_id_hash: str, run_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO posted_issues (issue_id_hash, run_id) VALUES (?, ?)",
            (issue_id_hash, run_id)
        )