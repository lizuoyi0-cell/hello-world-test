"""Board, list, and sharing management."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from .auth import ROLE_ADMIN, User
from .exceptions import NotFoundError, PermissionError_, ValidationError
from .logging_config import get_logger

log = get_logger("boards")

PERM_VIEW = "view"
PERM_EDIT = "edit"


@dataclass
class Board:
    id: int
    name: str
    description: str
    owner_id: int
    archived: bool
    created_at: str


@dataclass
class List_:
    id: int
    board_id: int
    name: str
    position: int
    archived: bool


def _row_to_board(row: sqlite3.Row) -> Board:
    return Board(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        owner_id=row["owner_id"],
        archived=bool(row["archived"]),
        created_at=row["created_at"],
    )


def _row_to_list(row: sqlite3.Row) -> List_:
    return List_(
        id=row["id"],
        board_id=row["board_id"],
        name=row["name"],
        position=row["position"],
        archived=bool(row["archived"]),
    )


class BoardService:
    """CRUD plus access control for boards and their lists."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- access checks ------------------------------------------------------

    def _permission(self, board_id: int, user: User) -> str:
        """Return ``'owner'``, ``'edit'``, ``'view'``, or raise."""
        if user.role == ROLE_ADMIN:
            return "owner"
        row = self.conn.execute(
            "SELECT owner_id FROM boards WHERE id=?", (board_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"board {board_id} not found")
        if row["owner_id"] == user.id:
            return "owner"
        share = self.conn.execute(
            "SELECT permission FROM board_shares WHERE board_id=? AND user_id=?",
            (board_id, user.id),
        ).fetchone()
        if share:
            return share["permission"]
        raise PermissionError_("no access to this board")

    def _require_edit(self, board_id: int, user: User) -> None:
        perm = self._permission(board_id, user)
        if perm == PERM_VIEW:
            raise PermissionError_("view-only access")

    # --- boards -------------------------------------------------------------

    def create_board(self, user: User, name: str, description: str = "") -> Board:
        if not name.strip():
            raise ValidationError("board name is required")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO boards(name,description,owner_id) VALUES(?,?,?)",
                (name.strip(), description, user.id),
            )
        log.info("board created id=%s by user=%s", cur.lastrowid, user.username)
        return self.get_board(cur.lastrowid, user)

    def get_board(self, board_id: int, user: User) -> Board:
        self._permission(board_id, user)
        row = self.conn.execute("SELECT * FROM boards WHERE id=?", (board_id,)).fetchone()
        if not row:
            raise NotFoundError(f"board {board_id} not found")
        return _row_to_board(row)

    def list_boards(self, user: User, include_archived: bool = False) -> list[Board]:
        if user.role == ROLE_ADMIN:
            sql = "SELECT b.* FROM boards b WHERE 1=1"
            params: tuple = ()
        else:
            sql = (
                "SELECT b.* FROM boards b "
                "LEFT JOIN board_shares s ON s.board_id=b.id AND s.user_id=? "
                "WHERE (b.owner_id=? OR s.user_id IS NOT NULL)"
            )
            params = (user.id, user.id)
        if not include_archived:
            sql += " AND b.archived=0"
        sql += " ORDER BY b.created_at DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_board(r) for r in rows]

    def update_board(
        self,
        board_id: int,
        user: User,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Board:
        self._require_edit(board_id, user)
        board = self.get_board(board_id, user)
        new_name = (name or board.name).strip()
        new_desc = description if description is not None else board.description
        if not new_name:
            raise ValidationError("board name is required")
        with self.conn:
            self.conn.execute(
                "UPDATE boards SET name=?, description=? WHERE id=?",
                (new_name, new_desc, board_id),
            )
        log.info("board updated id=%s", board_id)
        return self.get_board(board_id, user)

    def delete_board(self, board_id: int, user: User) -> None:
        perm = self._permission(board_id, user)
        if perm not in ("owner",):
            raise PermissionError_("only the owner can delete a board")
        with self.conn:
            self.conn.execute("DELETE FROM boards WHERE id=?", (board_id,))
        log.info("board deleted id=%s", board_id)

    def set_archived(self, board_id: int, user: User, archived: bool) -> Board:
        self._require_edit(board_id, user)
        with self.conn:
            self.conn.execute(
                "UPDATE boards SET archived=? WHERE id=?",
                (1 if archived else 0, board_id),
            )
        log.info("board %s archived=%s", board_id, archived)
        return self.get_board(board_id, user)

    # --- sharing ------------------------------------------------------------

    def share_board(
        self, board_id: int, owner: User, target_user_id: int, permission: str
    ) -> None:
        if permission not in (PERM_VIEW, PERM_EDIT):
            raise ValidationError("permission must be 'view' or 'edit'")
        if self._permission(board_id, owner) != "owner":
            raise PermissionError_("only the owner can share a board")
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO board_shares(board_id,user_id,permission) "
                "VALUES(?,?,?)",
                (board_id, target_user_id, permission),
            )
        log.info("board %s shared with user_id=%s perm=%s", board_id, target_user_id, permission)

    def unshare_board(self, board_id: int, owner: User, target_user_id: int) -> None:
        if self._permission(board_id, owner) != "owner":
            raise PermissionError_("only the owner can revoke sharing")
        with self.conn:
            self.conn.execute(
                "DELETE FROM board_shares WHERE board_id=? AND user_id=?",
                (board_id, target_user_id),
            )

    def list_shares(self, board_id: int, user: User) -> list[tuple[int, str]]:
        self._permission(board_id, user)
        rows = self.conn.execute(
            "SELECT user_id, permission FROM board_shares WHERE board_id=?",
            (board_id,),
        ).fetchall()
        return [(r["user_id"], r["permission"]) for r in rows]

    # --- lists --------------------------------------------------------------

    def create_list(self, board_id: int, user: User, name: str) -> List_:
        if not name.strip():
            raise ValidationError("list name is required")
        self._require_edit(board_id, user)
        pos = self.conn.execute(
            "SELECT COALESCE(MAX(position),-1)+1 AS p FROM lists WHERE board_id=?",
            (board_id,),
        ).fetchone()["p"]
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO lists(board_id,name,position) VALUES(?,?,?)",
                (board_id, name.strip(), pos),
            )
        log.info("list created id=%s on board=%s", cur.lastrowid, board_id)
        return self.get_list(cur.lastrowid, user)

    def get_list(self, list_id: int, user: User) -> List_:
        row = self.conn.execute("SELECT * FROM lists WHERE id=?", (list_id,)).fetchone()
        if not row:
            raise NotFoundError(f"list {list_id} not found")
        self._permission(row["board_id"], user)
        return _row_to_list(row)

    def list_lists(self, board_id: int, user: User, include_archived: bool = False) -> list[List_]:
        self._permission(board_id, user)
        sql = "SELECT * FROM lists WHERE board_id=?"
        if not include_archived:
            sql += " AND archived=0"
        sql += " ORDER BY position"
        rows = self.conn.execute(sql, (board_id,)).fetchall()
        return [_row_to_list(r) for r in rows]

    def update_list(self, list_id: int, user: User, name: str) -> List_:
        if not name.strip():
            raise ValidationError("list name is required")
        lst = self.get_list(list_id, user)
        self._require_edit(lst.board_id, user)
        with self.conn:
            self.conn.execute("UPDATE lists SET name=? WHERE id=?", (name.strip(), list_id))
        return self.get_list(list_id, user)

    def delete_list(self, list_id: int, user: User) -> None:
        lst = self.get_list(list_id, user)
        self._require_edit(lst.board_id, user)
        with self.conn:
            self.conn.execute("DELETE FROM lists WHERE id=?", (list_id,))
        log.info("list deleted id=%s", list_id)

    def reorder_lists(self, board_id: int, user: User, ordered_ids: list[int]) -> None:
        """Apply a new order. ``ordered_ids`` must be a permutation of the
        board's current list ids."""
        self._require_edit(board_id, user)
        existing = {l.id for l in self.list_lists(board_id, user, include_archived=True)}
        if set(ordered_ids) != existing:
            raise ValidationError("ordered_ids must match the board's lists exactly")
        with self.conn:
            for pos, list_id in enumerate(ordered_ids):
                self.conn.execute(
                    "UPDATE lists SET position=? WHERE id=?", (pos, list_id)
                )

    def archive_list(self, list_id: int, user: User, archived: bool) -> List_:
        lst = self.get_list(list_id, user)
        self._require_edit(lst.board_id, user)
        with self.conn:
            self.conn.execute(
                "UPDATE lists SET archived=? WHERE id=?",
                (1 if archived else 0, list_id),
            )
        return self.get_list(list_id, user)
