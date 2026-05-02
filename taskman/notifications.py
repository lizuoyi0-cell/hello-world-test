"""Console-based notification helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Iterable

from .auth import User
from .logging_config import get_logger

log = get_logger("notifications")


def upcoming_due_cards(
    conn: sqlite3.Connection, user: User, within_days: int = 3
) -> list[sqlite3.Row]:
    """Return rows for cards assigned to the user with due dates inside the window."""
    horizon = (datetime.utcnow() + timedelta(days=within_days)).isoformat()
    rows = conn.execute(
        "SELECT c.id, c.title, c.due_date FROM cards c "
        "WHERE c.assignee_id = ? AND c.due_date IS NOT NULL "
        "AND c.due_date <= ? ORDER BY c.due_date",
        (user.id, horizon),
    ).fetchall()
    return list(rows)


def print_notifications(rows: Iterable[sqlite3.Row]) -> int:
    count = 0
    for r in rows:
        print(f"[reminder] card #{r['id']} '{r['title']}' due {r['due_date']}")
        count += 1
    if count:
        log.info("printed %d notifications", count)
    return count
