"""
SQLite helper for the pipeline.

Single DB at <root>/ai/data.db, shared across all app-users (the `user` column
distinguishes them). Use `get_conn()` as a context manager — it enables foreign
keys per connection and commits/rolls back automatically.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import config

DB_PATH: Path = config.AI_DIR / "data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    user         TEXT NOT NULL,
    ig_name      TEXT NOT NULL,
    ig_username  TEXT NOT NULL,
    ig_password  TEXT NOT NULL,
    PRIMARY KEY (user, ig_name)
);

CREATE TABLE IF NOT EXISTS auto_comment (
    user         TEXT NOT NULL,
    group_name   TEXT NOT NULL,
    ig_name      TEXT NOT NULL,
    target       TEXT NOT NULL,
    PRIMARY KEY (user, group_name, ig_name, target),
    FOREIGN KEY (user, ig_name) REFERENCES accounts(user, ig_name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auto_comment_user_group
    ON auto_comment(user, group_name);
CREATE INDEX IF NOT EXISTS idx_auto_comment_user_igname
    ON auto_comment(user, ig_name);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    first_open = not DB_PATH.exists()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if first_open:
        init_schema(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
