"""Tests for AuthService."""

from __future__ import annotations

import pytest

from taskman.auth import AuthService, ROLE_USER
from taskman.exceptions import AuthError, DuplicateError, NotFoundError, ValidationError


def test_register_creates_user(auth: AuthService) -> None:
    user = auth.register("carol", "carol@example.com", "hunter22")
    assert user.id > 0
    assert user.username == "carol"
    assert user.role == ROLE_USER


def test_register_validates_inputs(auth: AuthService) -> None:
    with pytest.raises(ValidationError):
        auth.register("ab", "ab@example.com", "hunter22")
    with pytest.raises(ValidationError):
        auth.register("alice", "not-an-email", "hunter22")
    with pytest.raises(ValidationError):
        auth.register("alice", "alice@example.com", "12")


def test_register_duplicate_rejected(auth: AuthService, alice) -> None:
    with pytest.raises(DuplicateError):
        auth.register("alice", "other@example.com", "hunter22")


def test_login_logout(auth: AuthService, alice) -> None:
    session = auth.login("alice", "secret123")
    assert session.user.id == alice.id
    assert auth.whoami(session.token).id == alice.id
    auth.logout(session.token)
    with pytest.raises(AuthError):
        auth.whoami(session.token)


def test_login_wrong_password(auth: AuthService, alice) -> None:
    with pytest.raises(AuthError):
        auth.login("alice", "WRONG")


def test_password_reset_flow(auth: AuthService, alice, capsys) -> None:
    token = auth.request_password_reset("alice@example.com")
    capsys.readouterr()  # consume printed token
    auth.reset_password(token, "newsecret")
    with pytest.raises(AuthError):
        auth.login("alice", "secret123")
    session = auth.login("alice", "newsecret")
    assert session.user.username == "alice"


def test_password_reset_unknown_email(auth: AuthService) -> None:
    with pytest.raises(NotFoundError):
        auth.request_password_reset("ghost@example.com")


def test_update_profile_changes_email(auth: AuthService, alice) -> None:
    updated = auth.update_profile(alice.id, email="alice2@example.com")
    assert updated.email == "alice2@example.com"


def test_update_profile_change_password(auth: AuthService, alice) -> None:
    auth.update_profile(alice.id, password="newsecret")
    auth.login("alice", "newsecret")
