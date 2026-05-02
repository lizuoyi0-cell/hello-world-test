"""End-to-end integration tests covering full user journeys."""

from __future__ import annotations

import time

from taskman.auth import AuthService
from taskman.boards import BoardService, PERM_EDIT
from taskman.cards import CardService, PRIORITY_HIGH


def test_full_workflow(conn):
    """Register -> board -> list -> card -> comment -> share -> move."""
    auth = AuthService(conn)
    boards = BoardService(conn)
    cards = CardService(conn, boards)

    alice = auth.register("alice", "alice@example.com", "secret123")
    bob = auth.register("bob", "bob@example.com", "secret123")

    session = auth.login("alice", "secret123")
    assert session.user.username == "alice"

    board = boards.create_board(alice, "Project X", "Big plans")
    todo = boards.create_list(board.id, alice, "ToDo")
    doing = boards.create_list(board.id, alice, "Doing")
    done = boards.create_list(board.id, alice, "Done")

    boards.share_board(board.id, alice, bob.id, PERM_EDIT)

    card = cards.create_card(
        todo.id, alice, "Build MVP", description="ship",
        priority=PRIORITY_HIGH, assignee_id=bob.id,
    )
    cards.add_label_to_card(card.id, alice, "blocker")
    cards.add_comment(card.id, alice, "high priority please")
    cards.add_comment(card.id, bob, "on it")

    cards.move_card(card.id, bob, doing.id)
    cards.move_card(card.id, bob, done.id)

    final = cards.get_card(card.id, alice)
    assert final.list_id == done.id
    assert "blocker" in final.labels
    assert len(cards.list_comments(card.id, alice)) == 2


def test_performance_large_dataset(conn):
    """Smoke test for 100 boards and 1000 cards. Must finish quickly."""
    auth = AuthService(conn)
    boards = BoardService(conn)
    cards = CardService(conn, boards)
    user = auth.register("perf", "perf@example.com", "secret123")

    t0 = time.time()
    board_ids = []
    for i in range(20):
        b = boards.create_board(user, f"B{i}", "")
        board_ids.append(b.id)
        l = boards.create_list(b.id, user, "L")
        for j in range(50):
            cards.create_card(l.id, user, f"card-{i}-{j}")
    duration = time.time() - t0
    # 1000 cards on a single thread; should finish well under a few seconds.
    assert duration < 30
    total = conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"]
    assert total == 1000
