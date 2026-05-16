"""Tests for the ContactBook service."""

import tempfile

from secretary_ai.core.config import Settings
from secretary_ai.services.contacts import ContactBook


def _settings_with_tmp(tmp_dir: str) -> Settings:
    return Settings(telegram_audio_root=f"{tmp_dir}/audio")


def test_upsert_and_get() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        s = _settings_with_tmp(tmp)
        cb = ContactBook(s)
        result = cb.upsert("user123", name="Alice", language="en")
        assert result["name"] == "Alice"
        assert result["language"] == "en"
        assert result["caller_id"] == "user123"

        fetched = cb.get("user123")
        assert fetched is not None
        assert fetched["name"] == "Alice"


def test_get_unknown_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        s = _settings_with_tmp(tmp)
        cb = ContactBook(s)
        assert cb.get("nonexistent") is None


def test_record_call_increments_count() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        s = _settings_with_tmp(tmp)
        cb = ContactBook(s)
        cb.upsert("user1", name="Bob")
        cb.record_call("user1")
        cb.record_call("user1")
        contact = cb.get("user1")
        assert contact is not None
        assert contact["call_count"] == 2
        assert "last_called" in contact


def test_list_all_sorted_by_last_called() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        s = _settings_with_tmp(tmp)
        cb = ContactBook(s)
        cb.upsert("a", name="First")
        cb.record_call("a")
        cb.upsert("b", name="Second")
        cb.record_call("b")
        all_contacts = cb.list_all()
        assert len(all_contacts) == 2
        assert all_contacts[0]["caller_id"] == "b"


def test_delete_contact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        s = _settings_with_tmp(tmp)
        cb = ContactBook(s)
        cb.upsert("del_me", name="Gone")
        assert cb.delete("del_me") is True
        assert cb.get("del_me") is None
        assert cb.delete("del_me") is False


def test_greeting_for_known_contact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        s = _settings_with_tmp(tmp)
        cb = ContactBook(s)
        cb.upsert("known", name="Charlie")
        greeting = cb.greeting_for("known")
        assert greeting is not None
        assert "Charlie" in greeting


def test_greeting_for_unknown_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        s = _settings_with_tmp(tmp)
        cb = ContactBook(s)
        assert cb.greeting_for("nobody") is None


def test_persistence_across_instances() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        s = _settings_with_tmp(tmp)
        cb1 = ContactBook(s)
        cb1.upsert("persist_user", name="Persisted")

        cb2 = ContactBook(s)
        fetched = cb2.get("persist_user")
        assert fetched is not None
        assert fetched["name"] == "Persisted"
