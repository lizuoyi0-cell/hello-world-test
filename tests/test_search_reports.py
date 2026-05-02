"""Tests for search, reports, backup/restore, and notifications."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from taskman.cards import PRIORITY_HIGH
from taskman.notifications import upcoming_due_cards
from taskman.reports import (
    completion_rate,
    export_cards_csv,
    export_json,
    import_json,
    label_distribution,
    text_bar_chart,
    text_pie_chart,
)
from taskman.search import search_cards


def _seed(boards, cards, alice):
    board = boards.create_board(alice, "Work", "")
    todo = boards.create_list(board.id, alice, "ToDo")
    done = boards.create_list(board.id, alice, "Done")
    soon = (datetime.utcnow() + timedelta(days=1)).date().isoformat()
    far = (datetime.utcnow() + timedelta(days=10)).date().isoformat()
    c1 = cards.create_card(
        todo.id, alice, "fix bug", due_date=soon,
        priority=PRIORITY_HIGH, assignee_id=alice.id,
    )
    cards.add_label_to_card(c1.id, alice, "urgent")
    cards.create_card(done.id, alice, "ship feature", due_date=far)
    cards.create_card(todo.id, alice, "write docs")
    return board


def test_search_text(conn, boards, cards, alice):
    _seed(boards, cards, alice)
    results = search_cards(conn, alice, text="bug")
    assert [c.title for c in results] == ["fix bug"]


def test_search_label(conn, boards, cards, alice):
    _seed(boards, cards, alice)
    results = search_cards(conn, alice, label="urgent")
    assert len(results) == 1
    assert results[0].labels == ["urgent"]


def test_search_filter_priority(conn, boards, cards, alice):
    _seed(boards, cards, alice)
    results = search_cards(conn, alice, priority=PRIORITY_HIGH)
    assert all(c.priority == PRIORITY_HIGH for c in results)


def test_completion_and_label_charts(conn, boards, cards, alice):
    board = _seed(boards, cards, alice)
    rates = completion_rate(conn, board.id)
    assert rates == {"ToDo": 2, "Done": 1}
    labels = label_distribution(conn, board.id)
    assert labels == {"urgent": 1}


def test_text_charts():
    out = text_bar_chart({"a": 1, "b": 4})
    assert "a" in out and "b" in out
    pie = text_pie_chart({"a": 1, "b": 1})
    assert "50.0%" in pie
    assert text_bar_chart({}) == "(no data)"


def test_export_import_roundtrip(conn, boards, cards, alice, tmp_path):
    _seed(boards, cards, alice)
    backup = tmp_path / "b.json"
    export_json(conn, backup)
    payload = json.loads(backup.read_text())
    assert "cards" in payload and len(payload["cards"]) == 3
    # Wipe and restore.
    with conn:
        conn.execute("DELETE FROM cards")
    assert conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"] == 0
    import_json(conn, backup)
    assert conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"] == 3


def test_export_cards_csv(conn, boards, cards, alice, tmp_path):
    _seed(boards, cards, alice)
    out = export_cards_csv(conn, tmp_path / "out.csv")
    text = out.read_text()
    assert "fix bug" in text
    assert text.startswith("board,list,card_id")


def test_upcoming_due_cards(conn, boards, cards, alice):
    _seed(boards, cards, alice)
    rows = upcoming_due_cards(conn, alice, within_days=2)
    titles = [r["title"] for r in rows]
    assert "fix bug" in titles
    assert "ship feature" not in titles
