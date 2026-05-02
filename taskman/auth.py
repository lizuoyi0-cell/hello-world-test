"""User authentication and management.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib only). Sessions are
in-memory tokens issued at login. Password reset tokens are time-limited
and printed to the console to simulate email delivery.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .exceptions import AuthError, DuplicateError, NotFoundError, ValidationError
from .logging_config import get_logger

log = get_logger("auth")

ROLE_ADMIN = "admin"
ROLE_USER = "user"

PBKDF2_ITERATIONS = 120_000
RESET_TOKEN_TTL_MINUTES = 30
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class User:
    id: int
    username: str
    email: str
    role: str
    created_at: str


@dataclass
class Session:
    token: str
    user: User


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return digest.hex()


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        role=row["role"],
        created_at=row["created_at"],
    )


def _validate_credentials(username: str, email: str, password: str) -> None:
    if not username or len(username) < 3:
        raise ValidationError("username must be at least 3 characters")
    if not EMAIL_RE.match(email or ""):
        raise ValidationError("invalid email address")
    if not password or len(password) < 6:
        raise ValidationError("password must be at least 6 characters")


class AuthService:
    """Handles user lifecycle and session bookkeeping."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._sessions: dict[str, User] = {}

    # --- registration / login ----------------------------------------------

    def register(
        self, username: str, email: str, password: str, role: str = ROLE_USER
    ) -> User:
        _validate_credentials(username, email, password)
        if role not in (ROLE_ADMIN, ROLE_USER):
            raise ValidationError(f"unknown role: {role}")
        salt = secrets.token_hex(16)
        pw_hash = _hash_password(password, salt)
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO users(username,email,password_hash,salt,role) "
                    "VALUES(?,?,?,?,?)",
                    (username, email, pw_hash, salt, role),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateError("username or email already taken") from exc
        log.info("registered user %s (role=%s)", username, role)
        return self.get_user(cur.lastrowid)

    def login(self, username: str, password: str) -> Session:
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            raise AuthError("invalid credentials")
        expected = row["password_hash"]
        actual = _hash_password(password, row["salt"])
        if not hmac.compare_digest(expected, actual):
            raise AuthError("invalid credentials")
        user = _row_to_user(row)
        token = secrets.token_urlsafe(24)
        self._sessions[token] = user
        log.info("login: %s", user.username)
        return Session(token=token, user=user)

    def logout(self, token: str) -> None:
        user = self._sessions.pop(token, None)
        if user:
            log.info("logout: %s", user.username)

    def whoami(self, token: str) -> User:
        if token not in self._sessions:
            raise AuthError("not logged in")
        return self._sessions[token]

    # --- profile ------------------------------------------------------------

    def get_user(self, user_id: int) -> User:
        row = self.conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            raise NotFoundError(f"user {user_id} not found")
        return _row_to_user(row)

    def find_user(self, username: str) -> User:
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            raise NotFoundError(f"user '{username}' not found")
        return _row_to_user(row)

    def list_users(self) -> list[User]:
        rows = self.conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        return [_row_to_user(r) for r in rows]

    def update_profile(
        self,
        user_id: int,
        username: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
    ) -> User:
        user = self.get_user(user_id)
        new_username = username or user.username
        new_email = email or user.email
        if password is None:
            if not new_username or len(new_username) < 3:
                raise ValidationError("username must be at least 3 characters")
            if not EMAIL_RE.match(new_email):
                raise ValidationError("invalid email address")
        else:
            _validate_credentials(new_username, new_email, password)
        try:
            with self.conn:
                if password:
                    salt = secrets.token_hex(16)
                    pw_hash = _hash_password(password, salt)
                    self.conn.execute(
                        "UPDATE users SET username=?, email=?, password_hash=?, salt=? "
                        "WHERE id=?",
                        (new_username, new_email, pw_hash, salt, user_id),
                    )
                else:
                    self.conn.execute(
                        "UPDATE users SET username=?, email=? WHERE id=?",
                        (new_username, new_email, user_id),
                    )
        except sqlite3.IntegrityError as exc:
            raise DuplicateError("username or email already taken") from exc
        log.info("updated profile for user_id=%s", user_id)
        # Refresh any active sessions for this user.
        for tok, sess in list(self._sessions.items()):
            if sess.id == user_id:
                self._sessions[tok] = self.get_user(user_id)
        return self.get_user(user_id)

    # --- password reset -----------------------------------------------------

    def request_password_reset(self, email: str) -> str:
        """Issue a reset token and "send" it via console output."""
        row = self.conn.execute(
            "SELECT id, username FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not row:
            raise NotFoundError("no account with that email")
        token = secrets.token_urlsafe(16)
        expires = (
            datetime.utcnow() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
        ).isoformat()
        with self.conn:
            self.conn.execute(
                "UPDATE users SET reset_token=?, reset_expires=? WHERE id=?",
                (token, expires, row["id"]),
            )
        # Simulated email delivery.
        print(f"[email] To: {email}\n[email] Reset token: {token}")
        log.info("password reset requested for %s", email)
        return token

    def reset_password(self, token: str, new_password: str) -> None:
        if not new_password or len(new_password) < 6:
            raise ValidationError("password must be at least 6 characters")
        row = self.conn.execute(
            "SELECT id, reset_expires FROM users WHERE reset_token = ?", (token,)
        ).fetchone()
        if not row:
            raise AuthError("invalid reset token")
        expires = datetime.fromisoformat(row["reset_expires"])
        if expires < datetime.utcnow():
            raise AuthError("reset token expired")
        salt = secrets.token_hex(16)
        pw_hash = _hash_password(new_password, salt)
        with self.conn:
            self.conn.execute(
                "UPDATE users SET password_hash=?, salt=?, reset_token=NULL, "
                "reset_expires=NULL WHERE id=?",
                (pw_hash, salt, row["id"]),
            )
        log.info("password reset complete for user_id=%s", row["id"])
