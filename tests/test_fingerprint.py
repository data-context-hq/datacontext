from __future__ import annotations

from datacontext.fingerprint import fingerprint_query, normalize_query


def test_normalize_query_removes_literals() -> None:
    normalized = normalize_query("SELECT * FROM users WHERE id = 42 AND email = 'a@b.com'")

    assert normalized == "select * from users where id = ? and email = ?"
    assert "42" not in normalized
    assert "a@b.com" not in normalized


def test_fingerprint_is_stable_for_literal_changes() -> None:
    first = fingerprint_query("select * from users where id = 1")
    second = fingerprint_query("select * from users where id = 2")

    assert first == second
    assert first.startswith("sha256:")


def test_fingerprint_fails_closed() -> None:
    class BadQuery:
        def __str__(self) -> str:
            raise RuntimeError("secret raw sql")

    assert fingerprint_query(BadQuery()) == "unknown"

