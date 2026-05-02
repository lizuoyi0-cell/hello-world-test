"""Tests for BoardService."""

from __future__ import annotations

import pytest

from taskman.boards import BoardService, PERM_EDIT, PERM_VIEW
from taskman.exceptions import NotFoundError, PermissionError_, ValidationError


def test_create_and_get_board(boards: BoardService, alice) -> None:
    board = boards.create_board(alice, "Trip", "Vacation planning")
    fetched = boards.get_board(board.id, alice)
    assert fetched.name == "Trip"
    assert fetched.owner_id == alice.id
    assert fetched.archived is False


def test_create_board_requires_name(boards: BoardService, alice) -> None:
    with pytest.raises(ValidationError):
        boards.create_board(alice, "  ", "")


def test_other_user_cannot_access(boards: BoardService, alice, bob) -> None:
    board = boards.create_board(alice, "Private", "")
    with pytest.raises(PermissionError_):
        boards.get_board(board.id, bob)


def test_share_board_view_only(boards: BoardService, alice, bob) -> None:
    board = boards.create_board(alice, "Shared", "")
    boards.share_board(board.id, alice, bob.id, PERM_VIEW)
    assert boards.get_board(board.id, bob).id == board.id
    with pytest.raises(PermissionError_):
        boards.create_list(board.id, bob, "should fail")


def test_share_board_edit_allows_write(boards: BoardService, alice, bob) -> None:
    board = boards.create_board(alice, "Shared", "")
    boards.share_board(board.id, alice, bob.id, PERM_EDIT)
    lst = boards.create_list(board.id, bob, "ToDo")
    assert lst.board_id == board.id


def test_admin_sees_everything(boards: BoardService, alice, admin) -> None:
    board = boards.create_board(alice, "Alice's", "")
    assert boards.get_board(board.id, admin).id == board.id


def test_archive_unarchive(boards: BoardService, alice) -> None:
    board = boards.create_board(alice, "B", "")
    boards.set_archived(board.id, alice, True)
    assert board.id not in {b.id for b in boards.list_boards(alice)}
    assert board.id in {b.id for b in boards.list_boards(alice, include_archived=True)}


def test_only_owner_can_delete(boards: BoardService, alice, bob) -> None:
    board = boards.create_board(alice, "B", "")
    boards.share_board(board.id, alice, bob.id, PERM_EDIT)
    with pytest.raises(PermissionError_):
        boards.delete_board(board.id, bob)
    boards.delete_board(board.id, alice)
    with pytest.raises(NotFoundError):
        boards.get_board(board.id, alice)


def test_list_creation_and_reorder(boards: BoardService, alice) -> None:
    board = boards.create_board(alice, "Work", "")
    a = boards.create_list(board.id, alice, "A")
    b = boards.create_list(board.id, alice, "B")
    c = boards.create_list(board.id, alice, "C")
    boards.reorder_lists(board.id, alice, [c.id, a.id, b.id])
    ordered = [l.name for l in boards.list_lists(board.id, alice)]
    assert ordered == ["C", "A", "B"]


def test_reorder_rejects_mismatch(boards: BoardService, alice) -> None:
    board = boards.create_board(alice, "W", "")
    a = boards.create_list(board.id, alice, "A")
    with pytest.raises(ValidationError):
        boards.reorder_lists(board.id, alice, [a.id, 9999])
