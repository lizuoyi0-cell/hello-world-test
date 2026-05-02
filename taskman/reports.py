"""Reporting, backup, and restore.

Exports go to CSV/JSON. Charts are rendered in plain text (bar/pie) so the
project remains stdlib-only beyond the documented optional deps.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .logging_config import get_logger

log = get_logger("reports")

EXPORT_TABLES = (
    "users",
    "boards",
    "board_shares",
    "lists",
    "cards",
    "comments",
    "labels",
    "card_labels",
    "attachments",
)


def export_json(conn: sqlite3.Connection, path: Path | str) -> Path:
    """Dump every table to a single JSON file. Used as a backup format."""
    out: dict[str, list[dict[str, Any]]] = {}
    for table in EXPORT_TABLES:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        out[table] = [dict(r) for r in rows]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log.info("export_json -> %s (%d tables)", target, len(out))
    return target


def import_json(conn: sqlite3.Connection, path: Path | str) -> None:
    """Restore from a backup. Wipes existing rows in those tables first."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    with conn:
        for table in reversed(EXPORT_TABLES):
            conn.execute(f"DELETE FROM {table}")
        for table in EXPORT_TABLES:
            rows = data.get(table, [])
            if not rows:
                continue
            cols = list(rows[0].keys())
            placeholders = ",".join("?" for _ in cols)
            sql = f"INSERT INTO {table}({','.join(cols)}) VALUES({placeholders})"
            conn.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
    log.info("import_json from %s", path)


def export_cards_csv(conn: sqlite3.Connection, path: Path | str) -> Path:
    """Write a flat CSV with one row per card for spreadsheets/reporting."""
    rows = conn.execute(
        "SELECT b.name AS board, li.name AS list, c.id, c.title, c.description, "
        "c.due_date, c.priority, c.assignee_id, c.created_at "
        "FROM cards c JOIN lists li ON li.id=c.list_id "
        "JOIN boards b ON b.id=li.board_id ORDER BY b.name, li.position, c.position"
    ).fetchall()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["board", "list", "card_id", "title", "description", "due_date",
             "priority", "assignee_id", "created_at"]
        )
        for r in rows:
            writer.writerow([r[k] for k in r.keys()])
    log.info("export_cards_csv -> %s (%d rows)", target, len(rows))
    return target


# --- text-mode charts ----------------------------------------------------


def text_bar_chart(data: dict[str, int], width: int = 30) -> str:
    """Render a horizontal text bar chart for label/category counts."""
    if not data:
        return "(no data)"
    max_value = max(data.values()) or 1
    lines = []
    label_width = max(len(k) for k in data) if data else 0
    for label, value in data.items():
        bar = "#" * int((value / max_value) * width)
        lines.append(f"{label.ljust(label_width)} | {bar} {value}")
    return "\n".join(lines)


def text_pie_chart(data: dict[str, int]) -> str:
    """Approximate pie chart as a percentage breakdown."""
    total = sum(data.values())
    if not total:
        return "(no data)"
    lines = []
    for label, value in data.items():
        pct = (value / total) * 100
        lines.append(f"{label}: {pct:5.1f}%  ({value})")
    return "\n".join(lines)


def label_distribution(conn: sqlite3.Connection, board_id: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT l.name AS name, COUNT(*) AS n FROM labels l "
        "JOIN card_labels cl ON cl.label_id=l.id WHERE l.board_id=? "
        "GROUP BY l.name",
        (board_id,),
    ).fetchall()
    return {r["name"]: r["n"] for r in rows}


def completion_rate(conn: sqlite3.Connection, board_id: int) -> dict[str, int]:
    """Return card counts per list on a board (proxy for completion rate)."""
    rows = conn.execute(
        "SELECT li.name AS name, COUNT(c.id) AS n FROM lists li "
        "LEFT JOIN cards c ON c.list_id=li.id WHERE li.board_id=? GROUP BY li.id "
        "ORDER BY li.position",
        (board_id,),
    ).fetchall()
    return {r["name"]: r["n"] for r in rows}


# --- progress bar --------------------------------------------------------


def progress_bar(current: int, total: int, width: int = 30) -> str:
    """Return a `[###---]` style progress bar suitable for printing in-place."""
    if total <= 0:
        total = 1
    filled = int(width * current / total)
    return f"[{'#' * filled}{'-' * (width - filled)}] {current}/{total}"
