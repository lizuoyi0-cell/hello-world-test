# Taskman

A Trello-style task management system for the command line. Single-user or
multi-user, all data persisted to SQLite, all operations driven from a
nested menu CLI.

## Features

- **Auth & users** — registration, hashed passwords (PBKDF2-HMAC-SHA256),
  in-memory sessions, password reset via simulated email, profile updates,
  admin/user roles.
- **Boards & lists** — create, edit, archive, delete, reorder, share
  (view / edit) with other users.
- **Cards** — title, description, due date, priority, assignee, labels,
  comments, file attachments, cross-list moves, in-list reordering.
- **Search & filters** — text, label, assignee, priority, due-before,
  multiple sort orders.
- **Reports** — text-mode bar/pie charts for completion rate and label
  distribution; CSV export of cards; full JSON backup/restore.
- **Notifications** — console reminders for cards due within N days,
  printed at login.
- **i18n** — built-in English and Spanish strings.
- **Persistence** — SQLite with foreign keys, indexes, schema version
  table, simple migration plumbing, an LRU cache layer for hot reads.
- **Logging** — rotating file logs (`~/.taskman/taskman.log`) plus warning+
  console output.

## Installation

```sh
pip install -r requirements.txt
```

`colorama` is the only optional runtime dep — without it, the CLI still
works but is monochrome. `pytest`/`pytest-cov` are dev-only.

## Usage

```sh
python -m taskman                  # default DB at ~/.taskman/taskman.db
python -m taskman --db ./local.db  # use a project-local DB
```

The CLI walks you through registration, login, then board / list / card
management. Pick `5) help` from the main menu for a full command list.

### Example session

```
Welcome to Taskman v1.0.0
Main Menu
  1) Login
  2) Register
  ...
> 2
Username: alice
Email: alice@example.com
Password: ********
Registered. Please log in.
> 1
Logged in
-- alice (user) --
  1) Boards
  ...
> 1
c) create board
> c
name: Project X
description: Big plans
```

## Database schema

```
users (id, username U, email U, password_hash, salt, role, created_at,
       reset_token, reset_expires)
boards (id, name, description, owner_id -> users, archived, created_at)
board_shares (board_id -> boards, user_id -> users, permission)
lists (id, board_id -> boards, name, position, archived)
cards (id, list_id -> lists, title, description, due_date, priority,
       position, assignee_id -> users, created_at)
comments (id, card_id -> cards, user_id -> users, body, created_at)
labels (id, board_id -> boards, name, color)   UNIQUE(board_id, name)
card_labels (card_id -> cards, label_id -> labels)
attachments (id, card_id -> cards, file_path, filename, size, added_at)
audit_log (id, user_id, action, detail, created_at)
```

`U` = unique. All foreign keys cascade on delete (assignee_id is set NULL).

## Internal API reference

### `taskman.auth.AuthService`

| method | purpose |
| --- | --- |
| `register(username, email, password, role='user')` | create user |
| `login(username, password) -> Session` | issue session token |
| `logout(token)` | drop session |
| `whoami(token) -> User` | look up active session |
| `update_profile(user_id, username=, email=, password=)` | partial update |
| `request_password_reset(email) -> token` | print token to console |
| `reset_password(token, new_password)` | apply reset |
| `find_user(username) / get_user(id) / list_users()` | lookups |

### `taskman.boards.BoardService`

`create_board`, `get_board`, `list_boards`, `update_board`,
`delete_board`, `set_archived`, `share_board`, `unshare_board`,
`list_shares`, `create_list`, `get_list`, `list_lists`, `update_list`,
`delete_list`, `reorder_lists`, `archive_list`.

### `taskman.cards.CardService`

`create_card`, `get_card`, `list_cards`, `update_card`, `delete_card`,
`move_card`, `reorder_cards`, `add_comment`, `list_comments`,
`edit_comment`, `delete_comment`, `create_label`, `add_label_to_card`,
`remove_label_from_card`, `attach_file`, `list_attachments`,
`delete_attachment`.

### `taskman.search`

`search_cards(conn, user, *, text=, label=, assignee_id=, priority=, due_before=, sort_by=, descending=)`.

### `taskman.reports`

`export_json`, `import_json`, `export_cards_csv`, `text_bar_chart`,
`text_pie_chart`, `label_distribution`, `completion_rate`, `progress_bar`.

### `taskman.notifications`

`upcoming_due_cards(conn, user, within_days=3)` and
`print_notifications(rows)`.

### `taskman.i18n`

`set_language('en'|'es')`, `get_language()`, `t(key)`.

### Exceptions

All errors derive from `taskman.exceptions.TaskmanError`. Specific:
`ValidationError`, `AuthError`, `NotFoundError`, `PermissionError_`,
`DuplicateError`, `StorageError`.

## Testing

```sh
python -m pytest tests/ -q
python -m pytest tests/ --cov=taskman --cov-report=term-missing
```

48 tests cover unit (auth, boards, cards, search, reports, i18n, cache)
plus integration (full register→board→list→card→comment→share→move
workflow) and a 1000-card performance smoke test. The non-CLI service
layer is at ~81% line coverage.

## Contributing

1. Fork, branch (`feat/<topic>` or `fix/<topic>`).
2. Run `python -m pytest tests/ -q` before committing.
3. Format with `black taskman tests` (optional).
4. Lint with `pylint taskman` (optional).
5. Open a PR with a short description and rationale.

## License

MIT.
