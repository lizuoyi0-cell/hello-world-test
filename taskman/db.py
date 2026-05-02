"""SQLite persistence layer.

Owns the schema, migrations, connection management, and basic transaction
helpers. The schema is intentionally normalized with foreign keys and
indexes on commonly queried columns.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .exceptions import StorageError
from .logging_config import get_logger

log = get_logger("db")

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT    NOT NULL UNIQUE,
    email        TEXT    NOT NULL UNIQUE,
    password_hash TEXT   NOT NULL,
    salt         TEXT    NOT NULL,
    role         TEXT    NOT NULL DEFAULT 'user',
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reset_token  TEXT,
    reset_expires TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS boards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    owner_id    INTEGER NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_boards_owner ON boards(owner_id);

CREATE TABLE IF NOT EXISTS board_shares (
    board_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    permission TEXT    NOT NULL CHECK(permission IN ('view','edit')),
    PRIMARY KEY(board_id, user_id),
    FOREIGN KEY(board_id) REFERENCES boards(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id)  REFERENCES users(id)  ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lists (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id  INTEGER NOT NULL,
    name      TEXT    NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0,
    archived  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(board_id) REFERENCES boards(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_lists_board ON lists(board_id);

CREATE TABLE IF NOT EXISTS cards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id     INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    due_date    TEXT,
    priority    INTEGER NOT NULL DEFAULT 2,
    position    INTEGER NOT NULL DEFAULT 0,
    assignee_id INTEGER,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(list_id)     REFERENCES lists(id) ON DELETE CASCADE,
    FOREIGN KEY(assignee_id) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_list ON cards(list_id);
CREATE INDEX IF NOT EXISTS idx_cards_assignee ON cards(assignee_id);
CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(due_date);

CREATE TABLE IF NOT EXISTS comments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id   INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    body      TEXT    NOT NULL,
    created_at TEXT   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_comments_card ON comments(card_id);

CREATE TABLE IF NOT EXISTS labels (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL,
    name     TEXT    NOT NULL,
    color    TEXT    NOT NULL DEFAULT 'white',
    UNIQUE(board_id, name),
    FOREIGN KEY(board_id) REFERENCES boards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS card_labels (
    card_id  INTEGER NOT NULL,
    label_id INTEGER NOT NULL,
    PRIMARY KEY(card_id, label_id),
    FOREIGN KEY(card_id)  REFERENCES cards(id)  ON DELETE CASCADE,
    FOREIGN KEY(label_id) REFERENCES labels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attachments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id   INTEGER NOT NULL,
    file_path TEXT    NOT NULL,
    filename  TEXT    NOT NULL,
    size      INTEGER NOT NULL DEFAULT 0,
    added_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER,
    action    TEXT NOT NULL,
    detail    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def default_db_path() -> Path:
    return Path(os.environ.get("TASKMAN_DB", Path.home() / ".taskman" / "taskman.db"))


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with sane defaults (foreign keys, row dicts)."""
    path = Path(db_path) if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
    except sqlite3.Error as exc:
        raise StorageError(f"failed to open database {path}: {exc}") from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and stamp the schema version on a fresh database."""
    with conn:
        conn.executescript(SCHEMA)
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    log.debug("database initialized at version %s", SCHEMA_VERSION)


def migrate(conn: sqlite3.Connection) -> None:
    """Apply migrations. Currently a no-op since we are at v1, but the
    plumbing is in place for future versions."""
    cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
    row = cur.fetchone()
    current = row["version"] if row else 0
    if current < SCHEMA_VERSION:
        log.info("migrating database from v%s to v%s", current, SCHEMA_VERSION)
        with conn:
            conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Context manager that commits on success and rolls back on error."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def setup(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Convenience: open + init + migrate in a single call."""
    conn = connect(db_path)
    init_db(conn)
    migrate(conn)
    return conn
