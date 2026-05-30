"""Tests for the wake-word detection engine."""

import json

import pytest

from secretary_ai.core.config import Settings
from secretary_ai.services.wake_word import WakeWordEngine


@pytest.fixture()
def engine(tmp_path) -> WakeWordEngine:
    return WakeWordEngine(
        Settings(
            wake_word_enabled=True,
            wake_word_prefix="secretary",
            wake_word_aliases="",
            wake_word_require_prefix=False,
            wake_word_config_path=str(tmp_path / "wake_actions.json"),
        )
    )


def test_detects_restaurant_search(engine: WakeWordEngine) -> None:
    match = engine.detect("Find a restaurant near me")
    assert match is not None
    assert match.action == "find_restaurant"
    assert match.confidence > 0


def test_detects_hotel_search(engine: WakeWordEngine) -> None:
    match = engine.detect("I need to find a hotel in Paris")
    assert match is not None
    assert match.action == "find_hotel"


def test_detects_schedule_action(engine: WakeWordEngine) -> None:
    match = engine.detect("Schedule a meeting for tomorrow at 3pm")
    assert match is not None
    assert match.action == "schedule"


def test_detects_reminder_action(engine: WakeWordEngine) -> None:
    match = engine.detect("Remind me to call John at 5pm")
    assert match is not None
    assert match.action == "remind"


def test_detects_directions(engine: WakeWordEngine) -> None:
    match = engine.detect("Directions to the airport")
    assert match is not None
    assert match.action == "directions"
    assert "airport" in match.payload.lower()


def test_detects_event_search(engine: WakeWordEngine) -> None:
    match = engine.detect("Find tickets for concerts in London")
    assert match is not None
    assert match.action == "find_event"


def test_detects_travel_search(engine: WakeWordEngine) -> None:
    match = engine.detect("Find a flight to Barcelona")
    assert match is not None
    assert match.action == "find_travel"


def test_detects_evening_plan(engine: WakeWordEngine) -> None:
    match = engine.detect("Plan an evening out tonight")
    assert match is not None
    assert match.action == "plan_evening"


def test_detects_remember(engine: WakeWordEngine) -> None:
    match = engine.detect("Remember that my favourite colour is blue")
    assert match is not None
    assert match.action == "remember"


def test_returns_none_for_unmatched(engine: WakeWordEngine) -> None:
    match = engine.detect("What is the square root of 144?")
    assert match is None


def test_disabled_engine_returns_none(tmp_path) -> None:
    engine = WakeWordEngine(
        Settings(
            wake_word_enabled=False,
            wake_word_config_path=str(tmp_path / "w.json"),
        )
    )
    match = engine.detect("Find a restaurant")
    assert match is None


def test_wake_prefix_increases_confidence(engine: WakeWordEngine) -> None:
    no_prefix = engine.detect("Find a restaurant")
    with_prefix = engine.detect("Secretary, find a restaurant")
    assert no_prefix is not None
    assert with_prefix is not None
    assert with_prefix.confidence > no_prefix.confidence


def test_require_prefix_mode(tmp_path) -> None:
    engine = WakeWordEngine(
        Settings(
            wake_word_enabled=True,
            wake_word_prefix="secretary",
            wake_word_require_prefix=True,
            wake_word_config_path=str(tmp_path / "w.json"),
        )
    )
    assert engine.detect("Find a restaurant") is None
    match = engine.detect("Secretary, find a restaurant")
    assert match is not None
    assert match.action == "find_restaurant"


def test_custom_config_file(tmp_path) -> None:
    custom_actions = [
        {
            "action": "order_pizza",
            "phrases": ["order a pizza", "pizza delivery"],
            "description": "Order pizza.",
        }
    ]
    config_path = tmp_path / "custom_actions.json"
    config_path.write_text(json.dumps(custom_actions))

    engine = WakeWordEngine(
        Settings(
            wake_word_enabled=True,
            wake_word_prefix="secretary",
            wake_word_config_path=str(config_path),
        )
    )
    match = engine.detect("Order a pizza please")
    assert match is not None
    assert match.action == "order_pizza"


def test_wake_word_aliases(tmp_path) -> None:
    engine = WakeWordEngine(
        Settings(
            wake_word_enabled=True,
            wake_word_prefix="secretary",
            wake_word_aliases="hey sec,assistant",
            wake_word_require_prefix=True,
            wake_word_config_path=str(tmp_path / "w.json"),
        )
    )
    match = engine.detect("Hey sec, find a hotel")
    assert match is not None
    assert match.action == "find_hotel"


def test_list_actions(engine: WakeWordEngine) -> None:
    actions = engine.list_actions()
    assert isinstance(actions, list)
    assert len(actions) > 0
    action_names = [a["action"] for a in actions]
    assert "find_restaurant" in action_names
    assert "schedule" in action_names
    assert "remind" in action_names


def test_to_dict(engine: WakeWordEngine) -> None:
    match = engine.detect("Find a restaurant")
    assert match is not None
    d = match.to_dict()
    assert d["action"] == "find_restaurant"
    assert "payload" in d
    assert "wake_phrase" in d
    assert "confidence" in d


def test_empty_input(engine: WakeWordEngine) -> None:
    assert engine.detect("") is None
    assert engine.detect("   ") is None
