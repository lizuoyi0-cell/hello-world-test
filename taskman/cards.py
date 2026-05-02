"""Card (task) management: cards, comments, labels, attachments, reminders."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .auth import User
from .boards import BoardService
from .exceptions import NotFoundError, ValidationError
from .logging_config import get_logger

log = get_logger("cards")

PRIORITY_LOW = 1
PRIORITY_MEDIUM = 2
PRIORITY_HIGH = 3
PRIORITIES = {PRIORITY_LOW, PRIORITY_MEDIUM, PRIORITY_HIGH}
PRIORITY_NAMES = {PRIORITY_LOW: "low", PRIORITY_MEDIUM: "medium", PRIORITY_HIGH: "high"}


@dataclass
class Card:
    id: int
    list_id: int
    title: str
    description: str
    due_date: Optional[str]
    priority: int
    position: int
    assignee_id: Optional[int]
    created_at: str
    labels: list[str] = field(default_factory=list)


@dataclass
class Comment:
    id: int
    card_id: int
    user_id: int
    body: str
    created_at: str


@dataclass
class Attachment:
    id: int
    card_id: int
    file_path: str
    filename: str
    size: int
    added_at: str


def _row_to_card(row: sqlite3.Row, labels: Optional[list[str]] = None) -> Card:
    return Card(
        id=row["id"],
        list_id=row["list_id"],
        title=row["title"],
        description=row["description"],
        due_date=row["due_date"],
        priority=row["priority"],
        position=row["position"],
        assignee_id=row["assignee_id"],
        created_at=row["created_at"],
        labels=labels or [],
    )


class CardService:
    """All card lifecycle operations. Defers permission checks to BoardService."""

    def __init__(self, conn: sqlite3.Connection, boards: BoardService) -> None:
        self.conn = conn
        self.boards = boards

    # --- internal helpers ---------------------------------------------------

    def _board_id_for_list(self, list_id: int) -> int:
        row = self.conn.execute(
            "SELECT board_id FROM lists WHERE id=?", (list_id,)
        ).fetchone()
        if not row:
            raise NotFoundError(f"list {list_id} not found")
        return row["board_id"]

    def _board_id_for_card(self, card_id: int) -> int:
        row = self.conn.execute(
            "SELECT lists.board_id AS bid FROM cards "
            "JOIN lists ON lists.id = cards.list_id WHERE cards.id=?",
            (card_id,),
        ).fetchone()
        if not row:
            raise NotFoundError(f"card {card_id} not found")
        return row["bid"]

    def _labels_for(self, card_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT l.name FROM labels l JOIN card_labels cl ON cl.label_id=l.id "
            "WHERE cl.card_id=? ORDER BY l.name",
            (card_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    @staticmethod
    def _validate_due(due_date: Optional[str]) -> Optional[str]:
        if due_date in (None, ""):
            return None
        try:
            datetime.fromisoformat(due_date)
        except ValueError as exc:
            raise ValidationError("due_date must be ISO 8601 (YYYY-MM-DD or full)") from exc
        return due_date

    # --- card CRUD ----------------------------------------------------------

    def create_card(
        self,
        list_id: int,
        user: User,
        title: str,
        description: str = "",
        due_date: Optional[str] = None,
        priority: int = PRIORITY_MEDIUM,
        assignee_id: Optional[int] = None,
    ) -> Card:
        if not title.strip():
            raise ValidationError("card title is required")
        if priority not in PRIORITIES:
            raise ValidationError("priority must be 1, 2, or 3")
        due_date = self._validate_due(due_date)
        board_id = self._board_id_for_list(list_id)
        self.boards._require_edit(board_id, user)
        pos = self.conn.execute(
            "SELECT COALESCE(MAX(position),-1)+1 AS p FROM cards WHERE list_id=?",
            (list_id,),
        ).fetchone()["p"]
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO cards(list_id,title,description,due_date,priority,position,assignee_id)"
                " VALUES(?,?,?,?,?,?,?)",
                (list_id, title.strip(), description, due_date, priority, pos, assignee_id),
            )
        log.info("card created id=%s list=%s", cur.lastrowid, list_id)
        return self.get_card(cur.lastrowid, user)

    def get_card(self, card_id: int, user: User) -> Card:
        board_id = self._board_id_for_card(card_id)
        self.boards._permission(board_id, user)
        row = self.conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            raise NotFoundError(f"card {card_id} not found")
        return _row_to_card(row, self._labels_for(card_id))

    def list_cards(self, list_id: int, user: User) -> list[Card]:
        board_id = self._board_id_for_list(list_id)
        self.boards._permission(board_id, user)
        rows = self.conn.execute(
            "SELECT * FROM cards WHERE list_id=? ORDER BY position", (list_id,)
        ).fetchall()
        return [_row_to_card(r, self._labels_for(r["id"])) for r in rows]

    def update_card(
        self,
        card_id: int,
        user: User,
        title: Optional[str] = None,
        description: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[int] = None,
        assignee_id: Optional[int] = None,
    ) -> Card:
        card = self.get_card(card_id, user)
        board_id = self._board_id_for_card(card_id)
        self.boards._require_edit(board_id, user)
        new_title = (title or card.title).strip()
        if not new_title:
            raise ValidationError("card title is required")
        new_desc = card.description if description is None else description
        new_due = card.due_date if due_date is None else self._validate_due(due_date)
        new_pri = card.priority if priority is None else priority
        if new_pri not in PRIORITIES:
            raise ValidationError("priority must be 1, 2, or 3")
        new_assignee = card.assignee_id if assignee_id is None else assignee_id
        with self.conn:
            self.conn.execute(
                "UPDATE cards SET title=?, description=?, due_date=?, priority=?, "
                "assignee_id=? WHERE id=?",
                (new_title, new_desc, new_due, new_pri, new_assignee, card_id),
            )
        return self.get_card(card_id, user)

    def delete_card(self, card_id: int, user: User) -> None:
        board_id = self._board_id_for_card(card_id)
        self.boards._require_edit(board_id, user)
        with self.conn:
            self.conn.execute("DELETE FROM cards WHERE id=?", (card_id,))
        log.info("card deleted id=%s", card_id)

    def move_card(
        self, card_id: int, user: User, target_list_id: int, position: Optional[int] = None
    ) -> Card:
        card = self.get_card(card_id, user)
        src_board = self._board_id_for_card(card_id)
        dst_board = self._board_id_for_list(target_list_id)
        if src_board != dst_board:
            raise ValidationError("can only move cards within the same board")
        self.boards._require_edit(src_board, user)
        if position is None:
            position = self.conn.execute(
                "SELECT COALESCE(MAX(position),-1)+1 AS p FROM cards WHERE list_id=?",
                (target_list_id,),
            ).fetchone()["p"]
        with self.conn:
            self.conn.execute(
                "UPDATE cards SET list_id=?, position=? WHERE id=?",
                (target_list_id, position, card_id),
            )
        return self.get_card(card_id, user)

    def reorder_cards(self, list_id: int, user: User, ordered_ids: list[int]) -> None:
        board_id = self._board_id_for_list(list_id)
        self.boards._require_edit(board_id, user)
        rows = self.conn.execute(
            "SELECT id FROM cards WHERE list_id=?", (list_id,)
        ).fetchall()
        existing = {r["id"] for r in rows}
        if set(ordered_ids) != existing:
            raise ValidationError("ordered_ids must match the list's cards exactly")
        with self.conn:
            for pos, cid in enumerate(ordered_ids):
                self.conn.execute("UPDATE cards SET position=? WHERE id=?", (pos, cid))

    # --- comments -----------------------------------------------------------

    def add_comment(self, card_id: int, user: User, body: str) -> Comment:
        if not body.strip():
            raise ValidationError("comment body is required")
        board_id = self._board_id_for_card(card_id)
        self.boards._permission(board_id, user)
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO comments(card_id,user_id,body) VALUES(?,?,?)",
                (card_id, user.id, body.strip()),
            )
        row = self.conn.execute(
            "SELECT * FROM comments WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return Comment(
            id=row["id"],
            card_id=row["card_id"],
            user_id=row["user_id"],
            body=row["body"],
            created_at=row["created_at"],
        )

    def list_comments(self, card_id: int, user: User) -> list[Comment]:
        board_id = self._board_id_for_card(card_id)
        self.boards._permission(board_id, user)
        rows = self.conn.execute(
            "SELECT * FROM comments WHERE card_id=? ORDER BY created_at", (card_id,)
        ).fetchall()
        return [
            Comment(
                id=r["id"],
                card_id=r["card_id"],
                user_id=r["user_id"],
                body=r["body"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def edit_comment(self, comment_id: int, user: User, body: str) -> Comment:
        if not body.strip():
            raise ValidationError("comment body is required")
        row = self.conn.execute(
            "SELECT * FROM comments WHERE id=?", (comment_id,)
        ).fetchone()
        if not row:
            raise NotFoundError(f"comment {comment_id} not found")
        if row["user_id"] != user.id and user.role != "admin":
            from .exceptions import PermissionError_

            raise PermissionError_("can only edit your own comments")
        with self.conn:
            self.conn.execute(
                "UPDATE comments SET body=? WHERE id=?", (body.strip(), comment_id)
            )
        return self.list_comments(row["card_id"], user)[0]

    def delete_comment(self, comment_id: int, user: User) -> None:
        row = self.conn.execute(
            "SELECT user_id FROM comments WHERE id=?", (comment_id,)
        ).fetchone()
        if not row:
            raise NotFoundError(f"comment {comment_id} not found")
        if row["user_id"] != user.id and user.role != "admin":
            from .exceptions import PermissionError_

            raise PermissionError_("can only delete your own comments")
        with self.conn:
            self.conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))

    # --- labels -------------------------------------------------------------

    def create_label(self, board_id: int, user: User, name: str, color: str = "white") -> int:
        if not name.strip():
            raise ValidationError("label name is required")
        self.boards._require_edit(board_id, user)
        with self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO labels(board_id,name,color) VALUES(?,?,?)",
                (board_id, name.strip(), color),
            )
        if cur.lastrowid:
            return cur.lastrowid
        existing = self.conn.execute(
            "SELECT id FROM labels WHERE board_id=? AND name=?", (board_id, name.strip())
        ).fetchone()
        return existing["id"]

    def add_label_to_card(self, card_id: int, user: User, label_name: str) -> None:
        board_id = self._board_id_for_card(card_id)
        self.boards._require_edit(board_id, user)
        label_id = self.create_label(board_id, user, label_name)
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO card_labels(card_id,label_id) VALUES(?,?)",
                (card_id, label_id),
            )

    def remove_label_from_card(self, card_id: int, user: User, label_name: str) -> None:
        board_id = self._board_id_for_card(card_id)
        self.boards._require_edit(board_id, user)
        with self.conn:
            self.conn.execute(
                "DELETE FROM card_labels WHERE card_id=? AND label_id IN "
                "(SELECT id FROM labels WHERE board_id=? AND name=?)",
                (card_id, board_id, label_name),
            )

    # --- attachments --------------------------------------------------------

    def attach_file(self, card_id: int, user: User, file_path: str) -> Attachment:
        if not file_path.strip():
            raise ValidationError("file_path is required")
        board_id = self._board_id_for_card(card_id)
        self.boards._require_edit(board_id, user)
        filename = os.path.basename(file_path)
        try:
            size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        except OSError:
            size = 0
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO attachments(card_id,file_path,filename,size) VALUES(?,?,?,?)",
                (card_id, file_path, filename, size),
            )
        row = self.conn.execute(
            "SELECT * FROM attachments WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return Attachment(
            id=row["id"],
            card_id=row["card_id"],
            file_path=row["file_path"],
            filename=row["filename"],
            size=row["size"],
            added_at=row["added_at"],
        )

    def list_attachments(self, card_id: int, user: User) -> list[Attachment]:
        board_id = self._board_id_for_card(card_id)
        self.boards._permission(board_id, user)
        rows = self.conn.execute(
            "SELECT * FROM attachments WHERE card_id=? ORDER BY added_at", (card_id,)
        ).fetchall()
        return [
            Attachment(
                id=r["id"],
                card_id=r["card_id"],
                file_path=r["file_path"],
                filename=r["filename"],
                size=r["size"],
                added_at=r["added_at"],
            )
            for r in rows
        ]

    def delete_attachment(self, attachment_id: int, user: User) -> None:
        row = self.conn.execute(
            "SELECT card_id FROM attachments WHERE id=?", (attachment_id,)
        ).fetchone()
        if not row:
            raise NotFoundError(f"attachment {attachment_id} not found")
        board_id = self._board_id_for_card(row["card_id"])
        self.boards._require_edit(board_id, user)
        with self.conn:
            self.conn.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
