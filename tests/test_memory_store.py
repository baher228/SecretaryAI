from secretary_ai.core.config import Settings
from secretary_ai.services.memory_store import MemoryStore


def test_russian_user_fact_can_be_stored_and_retrieved(tmp_path) -> None:
    store = MemoryStore(Settings(telegram_audio_root=str(tmp_path / "audio")))

    record = store.add_user_fact_if_requested(
        "call-1",
        "Запомни, что моего врача зовут Анна",
    )
    matches = store.retrieve_user_fact("Как зовут моего врача?")

    assert record is not None
    assert record["fact"] == "моего врача зовут Анна"
    assert matches[0]["fact"] == "моего врача зовут Анна"
