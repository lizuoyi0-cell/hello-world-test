"""Search, filtering, and sorting helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from .auth import ROLE_ADMIN, User
from .cards import Card, _row_to_card


SORT_FIELDS = {"due_date", "priority", "created_at", "title", "position"}


def _accessible_board_filter(user: User) -> tuple[str, tuple]:
    """SQL fragment + params restricting cards to boards the user can access."""
    if user.role == ROLE_ADMIN:
        return "1=1", ()
    return (
        "(b.owner_id = ? OR EXISTS("
        "  SELECT 1 FROM board_shares s "
        "  WHERE s.board_id = b.id AND s.user_id = ?))",
        (user.id, user.id),
    )


def search_cards(
    conn: sqlite3.Connection,
    user: User,
    *,
    text: Optional[str] = None,
    label: Optional[str] = None,
    assignee_id: Optional[int] = None,
    priority: Optional[int] = None,
    due_before: Optional[str] = None,
    sort_by: str = "due_date",
    descending: bool = False,
) -> list[Card]:
    """Search cards across all boards the user can see.

    All filters are AND-combined. Empty filters are ignored.
    """
    if sort_by not in SORT_FIELDS:
        sort_by = "due_date"
    where, params = [], []
    perm_sql, perm_params = _accessible_board_filter(user)
    where.append(perm_sql)
    params.extend(perm_params)

    if text:
        where.append("(c.title LIKE ? OR c.description LIKE ?)")
        params.extend([f"%{text}%", f"%{text}%"])
    if assignee_id is not None:
        where.append("c.assignee_id = ?")
        params.append(assignee_id)
    if priority is not None:
        where.append("c.priority = ?")
        params.append(priority)
    if due_before:
        # Validate format early; raises ValueError if malformed.
        datetime.fromisoformat(due_before)
        where.append("c.due_date IS NOT NULL AND c.due_date <= ?")
        params.append(due_before)
    if label:
        where.append(
            "EXISTS(SELECT 1 FROM card_labels cl JOIN labels l ON l.id=cl.label_id "
            "WHERE cl.card_id=c.id AND l.name=?)"
        )
        params.append(label)

    sql = (
        "SELECT c.* FROM cards c "
        "JOIN lists li ON li.id = c.list_id "
        "JOIN boards b ON b.id = li.board_id "
        "WHERE " + " AND ".join(where) +
        f" ORDER BY c.{sort_by} {'DESC' if descending else 'ASC'}"
    )
    rows = conn.execute(sql, tuple(params)).fetchall()
    out: list[Card] = []
    for r in rows:
        labels = [
            x["name"]
            for x in conn.execute(
                "SELECT l.name FROM labels l JOIN card_labels cl ON cl.label_id=l.id "
                "WHERE cl.card_id=?",
                (r["id"],),
            ).fetchall()
        ]
        out.append(_row_to_card(r, labels))
    return out
