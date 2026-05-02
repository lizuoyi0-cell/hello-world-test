"""Tests for i18n, cache, and CLI helpers."""

from __future__ import annotations

import pytest

from taskman import i18n
from taskman.cache import bind, board_count, invalidate_all
from taskman.reports import progress_bar


def test_i18n_default_english():
    i18n.set_language("en")
    assert i18n.t("welcome") == "Welcome to Taskman"


def test_i18n_spanish_switch():
    i18n.set_language("es")
    assert i18n.t("welcome") == "Bienvenido a Taskman"
    i18n.set_language("en")


def test_i18n_unknown_lang():
    with pytest.raises(ValueError):
        i18n.set_language("xx")


def test_i18n_missing_key_falls_back():
    i18n.set_language("en")
    assert i18n.t("does.not.exist") == "does.not.exist"


def test_progress_bar():
    assert "0/10" in progress_bar(0, 10)
    full = progress_bar(10, 10, width=10)
    assert "##########" in full


def test_cache_board_count(conn, boards, alice):
    bind(conn)
    invalidate_all()
    assert board_count(alice.id) == 0
    boards.create_board(alice, "X", "")
    # Without invalidation the cache still returns the old result.
    assert board_count(alice.id) == 0
    invalidate_all()
    assert board_count(alice.id) == 1
