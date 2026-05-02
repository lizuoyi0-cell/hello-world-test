"""Menu-driven command line interface for taskman."""

from __future__ import annotations

import getpass
import readline  # noqa: F401  (enables history/autocomplete on input())
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from . import __version__, i18n
from .auth import AuthService, ROLE_ADMIN, ROLE_USER, Session, User
from .boards import BoardService, PERM_EDIT, PERM_VIEW
from .cache import bind as bind_cache
from .cards import CardService, PRIORITY_NAMES
from .db import setup
from .exceptions import TaskmanError
from .logging_config import configure_logging, get_logger
from .notifications import print_notifications, upcoming_due_cards
from .reports import (
    completion_rate,
    export_cards_csv,
    export_json,
    import_json,
    label_distribution,
    progress_bar,
    text_bar_chart,
    text_pie_chart,
)
from .search import search_cards

log = get_logger("cli")

# Optional colorama -- gracefully degrade if not installed.
try:
    from colorama import Fore, Style, init as colorama_init  # type: ignore

    colorama_init()
    HAS_COLOR = True
except ImportError:  # pragma: no cover - optional dep
    HAS_COLOR = False

    class _Stub:
        def __getattr__(self, _name: str) -> str:
            return ""

    Fore = _Stub()  # type: ignore
    Style = _Stub()  # type: ignore


HELP_TEXT = """
Taskman commands (top-level menu):
  1) login        - sign in to an existing account
  2) register     - create a new account
  3) reset-pw     - request and apply a password reset
  4) language     - switch UI language (en/es)
  5) help         - show this help message
  0) exit         - quit the program

Once logged in:
  boards          - browse, create, share, archive boards
  profile         - update your username, email, or password
  search          - search cards across all boards you can see
  reports         - export CSV/JSON, view label/completion charts
  backup/restore  - dump or load the entire database

Card priorities: 1=low, 2=medium, 3=high
Due dates use ISO 8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
""".strip()


# ---------------------------------------------------------------------------
# small UI helpers
# ---------------------------------------------------------------------------


def color(text: str, fore: str = "", bright: bool = False) -> str:
    if not HAS_COLOR or not fore:
        return text
    prefix = fore + (Style.BRIGHT if bright else "")
    return f"{prefix}{text}{Style.RESET_ALL}"


def prompt(label: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{label}{suffix}: ").strip()
    return raw or (default or "")


def prompt_int(label: str, default: Optional[int] = None) -> Optional[int]:
    raw = prompt(label, str(default) if default is not None else None)
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        print(color("not a number", Fore.RED))
        return None


def confirm(label: str) -> bool:
    return prompt(f"{label} (y/N)").lower().startswith("y")


def show_progress(message: str, steps: int = 20, delay: float = 0.02) -> None:
    """Render a fake progress bar for long-running operations."""
    for i in range(steps + 1):
        sys.stdout.write("\r" + message + " " + progress_bar(i, steps))
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# CLI app
# ---------------------------------------------------------------------------


class TaskmanCLI:
    """Owns the long-lived services and runs the interactive REPL."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        configure_logging()
        self.conn = setup(db_path)
        bind_cache(self.conn)
        self.auth = AuthService(self.conn)
        self.boards = BoardService(self.conn)
        self.cards = CardService(self.conn, self.boards)
        self.session: Optional[Session] = None

    # --- entry --------------------------------------------------------------

    def run(self) -> int:
        print(color(f"{i18n.t('welcome')} v{__version__}", Fore.CYAN, bright=True))
        try:
            while True:
                if self.session is None:
                    if not self._guest_menu():
                        break
                else:
                    if not self._user_menu():
                        break
        except (KeyboardInterrupt, EOFError):
            print()
        print(i18n.t("msg.bye"))
        return 0

    # --- guest --------------------------------------------------------------

    def _guest_menu(self) -> bool:
        print()
        print(color(i18n.t("menu.main"), Fore.YELLOW, bright=True))
        print(f"  1) {i18n.t('menu.login')}")
        print(f"  2) {i18n.t('menu.register')}")
        print("  3) reset password")
        print("  4) language (current: " + i18n.get_language() + ")")
        print(f"  5) {i18n.t('menu.help')}")
        print(f"  0) {i18n.t('menu.exit')}")
        choice = prompt(i18n.t("prompt.choice"))
        actions: dict[str, Callable[[], bool]] = {
            "1": self._do_login,
            "2": self._do_register,
            "3": self._do_password_reset,
            "4": self._do_language,
            "5": self._do_help,
            "0": lambda: False,
        }
        action = actions.get(choice)
        if action is None:
            print(color(i18n.t("msg.invalid"), Fore.RED))
            return True
        return action()

    def _do_login(self) -> bool:
        username = prompt(i18n.t("prompt.username"))
        password = getpass.getpass(i18n.t("prompt.password") + ": ")
        try:
            self.session = self.auth.login(username, password)
            print(color(i18n.t("msg.login_ok"), Fore.GREEN))
            self._show_login_notifications()
        except TaskmanError as exc:
            print(color(f"{i18n.t('msg.login_fail')}: {exc}", Fore.RED))
        return True

    def _do_register(self) -> bool:
        username = prompt(i18n.t("prompt.username"))
        email = prompt(i18n.t("prompt.email"))
        password = getpass.getpass(i18n.t("prompt.password") + ": ")
        try:
            self.auth.register(username, email, password, role=ROLE_USER)
            print(color("Registered. Please log in.", Fore.GREEN))
        except TaskmanError as exc:
            print(color(f"error: {exc}", Fore.RED))
        return True

    def _do_password_reset(self) -> bool:
        email = prompt(i18n.t("prompt.email"))
        try:
            self.auth.request_password_reset(email)
        except TaskmanError as exc:
            print(color(f"error: {exc}", Fore.RED))
            return True
        token = prompt("paste token from email")
        new_password = getpass.getpass("new password: ")
        try:
            self.auth.reset_password(token, new_password)
            print(color("Password updated.", Fore.GREEN))
        except TaskmanError as exc:
            print(color(f"error: {exc}", Fore.RED))
        return True

    def _do_language(self) -> bool:
        lang = prompt("language code (en/es)", i18n.get_language())
        try:
            i18n.set_language(lang)
        except ValueError as exc:
            print(color(f"error: {exc}", Fore.RED))
        return True

    def _do_help(self) -> bool:
        print(HELP_TEXT)
        return True

    # --- logged in ----------------------------------------------------------

    def _show_login_notifications(self) -> None:
        assert self.session
        rows = upcoming_due_cards(self.conn, self.session.user, within_days=3)
        if rows:
            print(color(f"You have {len(rows)} cards due soon:", Fore.MAGENTA))
            print_notifications(rows)

    def _user_menu(self) -> bool:
        assert self.session
        user = self.session.user
        print()
        print(color(f"-- {user.username} ({user.role}) --", Fore.CYAN))
        print(f"  1) {i18n.t('menu.boards')}")
        print(f"  2) {i18n.t('menu.profile')}")
        print(f"  3) {i18n.t('menu.search')}")
        print(f"  4) {i18n.t('menu.reports')}")
        print("  5) backup")
        print("  6) restore")
        if user.role == ROLE_ADMIN:
            print("  7) admin: list users")
        print(f"  8) {i18n.t('menu.help')}")
        print(f"  9) {i18n.t('menu.logout')}")
        print(f"  0) {i18n.t('menu.exit')}")
        choice = prompt(i18n.t("prompt.choice"))
        if choice == "1":
            self._boards_menu()
        elif choice == "2":
            self._profile_menu()
        elif choice == "3":
            self._search_menu()
        elif choice == "4":
            self._reports_menu()
        elif choice == "5":
            self._backup()
        elif choice == "6":
            self._restore()
        elif choice == "7" and user.role == ROLE_ADMIN:
            self._admin_list_users()
        elif choice == "8":
            self._do_help()
        elif choice == "9":
            self.auth.logout(self.session.token)
            self.session = None
        elif choice == "0":
            return False
        else:
            print(color(i18n.t("msg.invalid"), Fore.RED))
        return True

    # --- boards menu --------------------------------------------------------

    def _boards_menu(self) -> None:
        assert self.session
        user = self.session.user
        while True:
            boards = self.boards.list_boards(user)
            print()
            print(color("Boards:", Fore.YELLOW))
            for b in boards:
                print(f"  [{b.id}] {b.name} - {b.description}")
            print("  c) create board    o) open board    d) delete board")
            print("  a) archive toggle  s) share          q) back")
            choice = prompt("action")
            try:
                if choice == "c":
                    name = prompt("name")
                    desc = prompt("description", "")
                    self.boards.create_board(user, name, desc)
                elif choice == "o":
                    bid = prompt_int("board id")
                    if bid is not None:
                        self._board_detail(bid)
                elif choice == "d":
                    bid = prompt_int("board id")
                    if bid is not None and confirm("delete board?"):
                        self.boards.delete_board(bid, user)
                elif choice == "a":
                    bid = prompt_int("board id")
                    if bid is None:
                        continue
                    board = self.boards.get_board(bid, user)
                    self.boards.set_archived(bid, user, not board.archived)
                elif choice == "s":
                    self._share_board()
                elif choice == "q":
                    return
                else:
                    print(color(i18n.t("msg.invalid"), Fore.RED))
            except TaskmanError as exc:
                print(color(f"error: {exc}", Fore.RED))

    def _share_board(self) -> None:
        assert self.session
        user = self.session.user
        bid = prompt_int("board id")
        if bid is None:
            return
        target = prompt("share with username")
        target_user = self.auth.find_user(target)
        perm = prompt("permission (view/edit)", PERM_VIEW)
        self.boards.share_board(bid, user, target_user.id, perm)
        print(color("shared", Fore.GREEN))

    def _board_detail(self, board_id: int) -> None:
        assert self.session
        user = self.session.user
        while True:
            board = self.boards.get_board(board_id, user)
            print()
            print(color(f"Board #{board.id} {board.name}", Fore.YELLOW, bright=True))
            print(f"  {board.description}")
            for lst in self.boards.list_lists(board_id, user):
                print(f"  - List #{lst.id} {lst.name} (pos {lst.position})")
                for c in self.cards.list_cards(lst.id, user):
                    due = c.due_date or "-"
                    pri = PRIORITY_NAMES.get(c.priority, "?")
                    print(f"      * #{c.id} [{pri}] {c.title} (due {due})")
            print("\n  cl) new list   ce) edit list  cd) delete list  cr) reorder lists")
            print("  nc) new card   ec) edit card  dc) delete card  mc) move card")
            print("  cm) comment    lb) label      at) attach file  q) back")
            choice = prompt("action")
            try:
                if choice == "cl":
                    self.boards.create_list(board_id, user, prompt("list name"))
                elif choice == "ce":
                    lid = prompt_int("list id")
                    if lid is not None:
                        self.boards.update_list(lid, user, prompt("new name"))
                elif choice == "cd":
                    lid = prompt_int("list id")
                    if lid is not None and confirm("delete list?"):
                        self.boards.delete_list(lid, user)
                elif choice == "cr":
                    raw = prompt("ordered list ids comma-separated")
                    ids = [int(x) for x in raw.split(",") if x.strip()]
                    self.boards.reorder_lists(board_id, user, ids)
                elif choice == "nc":
                    self._new_card_flow()
                elif choice == "ec":
                    self._edit_card_flow()
                elif choice == "dc":
                    cid = prompt_int("card id")
                    if cid is not None and confirm("delete card?"):
                        self.cards.delete_card(cid, user)
                elif choice == "mc":
                    cid = prompt_int("card id")
                    tlid = prompt_int("target list id")
                    if cid is not None and tlid is not None:
                        self.cards.move_card(cid, user, tlid)
                elif choice == "cm":
                    cid = prompt_int("card id")
                    if cid is not None:
                        self.cards.add_comment(cid, user, prompt("comment"))
                elif choice == "lb":
                    cid = prompt_int("card id")
                    if cid is not None:
                        self.cards.add_label_to_card(cid, user, prompt("label"))
                elif choice == "at":
                    cid = prompt_int("card id")
                    if cid is not None:
                        self.cards.attach_file(cid, user, prompt("file path"))
                elif choice == "q":
                    return
                else:
                    print(color(i18n.t("msg.invalid"), Fore.RED))
            except TaskmanError as exc:
                print(color(f"error: {exc}", Fore.RED))

    def _new_card_flow(self) -> None:
        assert self.session
        user = self.session.user
        lid = prompt_int("list id")
        if lid is None:
            return
        title = prompt("title")
        desc = prompt("description", "")
        due = prompt("due date (ISO, blank for none)", "")
        pri = prompt_int("priority (1=low,2=med,3=high)", 2) or 2
        assignee_name = prompt("assignee username (blank for none)", "")
        assignee_id = (
            self.auth.find_user(assignee_name).id if assignee_name else None
        )
        self.cards.create_card(
            lid, user, title, desc,
            due_date=due or None, priority=pri, assignee_id=assignee_id,
        )

    def _edit_card_flow(self) -> None:
        assert self.session
        user = self.session.user
        cid = prompt_int("card id")
        if cid is None:
            return
        card = self.cards.get_card(cid, user)
        title = prompt("title", card.title)
        desc = prompt("description", card.description)
        due = prompt("due date", card.due_date or "")
        pri_raw = prompt("priority", str(card.priority))
        pri = int(pri_raw) if pri_raw else card.priority
        self.cards.update_card(
            cid, user, title=title, description=desc,
            due_date=due or "", priority=pri,
        )

    # --- profile -----------------------------------------------------------

    def _profile_menu(self) -> None:
        assert self.session
        user = self.session.user
        print(f"  username: {user.username}")
        print(f"  email:    {user.email}")
        print(f"  role:     {user.role}")
        new_username = prompt("new username", user.username)
        new_email = prompt("new email", user.email)
        change_pw = confirm("change password?")
        new_pw = getpass.getpass("new password: ") if change_pw else None
        try:
            self.auth.update_profile(
                user.id, username=new_username, email=new_email, password=new_pw
            )
            self.session.user.username = new_username  # type: ignore[misc]
            print(color("profile updated", Fore.GREEN))
        except TaskmanError as exc:
            print(color(f"error: {exc}", Fore.RED))

    # --- search ------------------------------------------------------------

    def _search_menu(self) -> None:
        assert self.session
        user = self.session.user
        text = prompt("text contains (blank skip)", "")
        label = prompt("label (blank skip)", "")
        sort_by = prompt("sort by (due_date/priority/title/created_at)", "due_date")
        try:
            results = search_cards(
                self.conn, user,
                text=text or None, label=label or None, sort_by=sort_by,
            )
        except (ValueError, TaskmanError) as exc:
            print(color(f"error: {exc}", Fore.RED))
            return
        for c in results:
            tag = ",".join(c.labels) if c.labels else "-"
            print(f"  #{c.id} {c.title} due={c.due_date} pri={c.priority} labels={tag}")
        print(f"({len(results)} results)")

    # --- reports -----------------------------------------------------------

    def _reports_menu(self) -> None:
        assert self.session
        user = self.session.user
        bid = prompt_int("board id")
        if bid is None:
            return
        self.boards.get_board(bid, user)  # access check
        print(color("Completion (cards per list):", Fore.CYAN))
        print(text_bar_chart(completion_rate(self.conn, bid)))
        print(color("\nLabel distribution:", Fore.CYAN))
        print(text_pie_chart(label_distribution(self.conn, bid)))
        if confirm("export CSV?"):
            path = prompt("path", "cards.csv")
            export_cards_csv(self.conn, path)
            print(color(f"wrote {path}", Fore.GREEN))

    # --- backup ------------------------------------------------------------

    def _backup(self) -> None:
        path = prompt("backup path", "taskman-backup.json")
        show_progress("Backing up", steps=15)
        export_json(self.conn, path)
        print(color(f"backup written to {path}", Fore.GREEN))

    def _restore(self) -> None:
        path = prompt("backup path", "taskman-backup.json")
        if not confirm(f"restore from {path}? this overwrites all data"):
            return
        show_progress("Restoring", steps=15)
        import_json(self.conn, path)
        print(color("restore complete", Fore.GREEN))

    # --- admin -------------------------------------------------------------

    def _admin_list_users(self) -> None:
        for u in self.auth.list_users():
            print(f"  [{u.id}] {u.username} ({u.role}) - {u.email}")


def main(argv: Optional[list[str]] = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    db_path: Optional[Path] = None
    if "--db" in args:
        idx = args.index("--db")
        db_path = Path(args[idx + 1])
    cli = TaskmanCLI(db_path=db_path)
    return cli.run()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
