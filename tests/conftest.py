"""Shared fixtures for taskman tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from taskman.auth import AuthService, ROLE_ADMIN, ROLE_USER
from taskman.boards import BoardService
from taskman.cards import CardService
from taskman.db import setup


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path):
    c = setup(db_path)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def auth(conn):
    return AuthService(conn)


@pytest.fixture
def boards(conn):
    return BoardService(conn)


@pytest.fixture
def cards(conn, boards):
    return CardService(conn, boards)


@pytest.fixture
def alice(auth):
    return auth.register("alice", "alice@example.com", "secret123")


@pytest.fixture
def bob(auth):
    return auth.register("bob", "bob@example.com", "secret123")


@pytest.fixture
def admin(auth):
    return auth.register("root", "root@example.com", "rootpass", role=ROLE_ADMIN)
