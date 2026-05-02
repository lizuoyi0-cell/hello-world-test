"""Tests for CardService."""

from __future__ import annotations

import pytest

from taskman.cards import (
    CardService,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
)
from taskman.exceptions import NotFoundError, PermissionError_, ValidationError


@pytest.fixture
def board(boards, alice):
    return boards.create_board(alice, "Work", "")


@pytest.fixture
def todo(boards, alice, board):
    return boards.create_list(board.id, alice, "ToDo")


@pytest.fixture
def doing(boards, alice, board):
    return boards.create_list(board.id, alice, "Doing")


def test_create_card(cards: CardService, alice, todo) -> None:
    card = cards.create_card(todo.id, alice, "Write tests", priority=PRIORITY_HIGH)
    assert card.title == "Write tests"
    assert card.priority == PRIORITY_HIGH
    assert card.list_id == todo.id


def test_card_validates_title(cards: CardService, alice, todo) -> None:
    with pytest.raises(ValidationError):
        cards.create_card(todo.id, alice, "  ")


def test_card_validates_priority(cards: CardService, alice, todo) -> None:
    with pytest.raises(ValidationError):
        cards.create_card(todo.id, alice, "X", priority=99)


def test_card_validates_due(cards: CardService, alice, todo) -> None:
    with pytest.raises(ValidationError):
        cards.create_card(todo.id, alice, "X", due_date="not-a-date")


def test_move_card(cards: CardService, alice, todo, doing) -> None:
    card = cards.create_card(todo.id, alice, "Task")
    moved = cards.move_card(card.id, alice, doing.id)
    assert moved.list_id == doing.id


def test_move_card_across_boards_rejected(cards: CardService, boards, alice, todo) -> None:
    other_board = boards.create_board(alice, "Other", "")
    other_list = boards.create_list(other_board.id, alice, "L")
    card = cards.create_card(todo.id, alice, "Task")
    with pytest.raises(ValidationError):
        cards.move_card(card.id, alice, other_list.id)


def test_reorder_cards(cards: CardService, alice, todo) -> None:
    a = cards.create_card(todo.id, alice, "A")
    b = cards.create_card(todo.id, alice, "B")
    c = cards.create_card(todo.id, alice, "C")
    cards.reorder_cards(todo.id, alice, [c.id, a.id, b.id])
    ordered = [card.title for card in cards.list_cards(todo.id, alice)]
    assert ordered == ["C", "A", "B"]


def test_comments(cards: CardService, alice, todo) -> None:
    card = cards.create_card(todo.id, alice, "X")
    cm = cards.add_comment(card.id, alice, "first")
    assert cm.body == "first"
    cards.edit_comment(cm.id, alice, "edited")
    comments = cards.list_comments(card.id, alice)
    assert comments[0].body == "edited"
    cards.delete_comment(cm.id, alice)
    assert cards.list_comments(card.id, alice) == []


def test_comment_permissions(cards: CardService, boards, alice, bob, todo) -> None:
    card = cards.create_card(todo.id, alice, "X")
    boards.share_board(todo.board_id, alice, bob.id, "edit")
    cm = cards.add_comment(card.id, bob, "from bob")
    with pytest.raises(PermissionError_):
        cards.delete_comment(cm.id, alice)


def test_labels_attach_and_remove(cards: CardService, alice, todo, board) -> None:
    card = cards.create_card(todo.id, alice, "X")
    cards.add_label_to_card(card.id, alice, "urgent")
    cards.add_label_to_card(card.id, alice, "backend")
    refreshed = cards.get_card(card.id, alice)
    assert set(refreshed.labels) == {"urgent", "backend"}
    cards.remove_label_from_card(card.id, alice, "urgent")
    refreshed = cards.get_card(card.id, alice)
    assert refreshed.labels == ["backend"]


def test_attachments(cards: CardService, alice, todo, tmp_path) -> None:
    sample = tmp_path / "doc.txt"
    sample.write_text("hi")
    card = cards.create_card(todo.id, alice, "X")
    att = cards.attach_file(card.id, alice, str(sample))
    assert att.filename == "doc.txt"
    assert att.size == 2
    listed = cards.list_attachments(card.id, alice)
    assert len(listed) == 1


def test_view_only_user_cannot_create_card(cards: CardService, boards, alice, bob, todo) -> None:
    boards.share_board(todo.board_id, alice, bob.id, "view")
    with pytest.raises(PermissionError_):
        cards.create_card(todo.id, bob, "nope")


def test_unknown_list(cards: CardService, alice) -> None:
    with pytest.raises(NotFoundError):
        cards.create_card(99999, alice, "X")
