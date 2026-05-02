"""Lightweight cache for read-heavy lookups.

Wraps a few common board/list reads with ``functools.lru_cache``. The cache
is keyed on the raw IDs so the caller has to remember to invalidate when
something changes -- :func:`invalidate_all` clears everything.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=256)
def cached_board_name(conn_id: int, board_id: int, _conn_token: int = 0) -> Optional[str]:
    """Stub that exists to demonstrate cache wiring; replaced at runtime."""
    return None


_CONN: sqlite3.Connection | None = None


def bind(conn: sqlite3.Connection) -> None:
    """Bind the cache helpers to a connection. Subsequent reads use it."""
    global _CONN
    _CONN = conn
    invalidate_all()


def invalidate_all() -> None:
    cached_board_name.cache_clear()
    _board_count.cache_clear()


@lru_cache(maxsize=64)
def _board_count(owner_id: int) -> int:
    if _CONN is None:
        return 0
    row = _CONN.execute(
        "SELECT COUNT(*) AS n FROM boards WHERE owner_id=?", (owner_id,)
    ).fetchone()
    return row["n"]


def board_count(owner_id: int) -> int:
    """Return the number of boards an owner has, with caching."""
    return _board_count(owner_id)
