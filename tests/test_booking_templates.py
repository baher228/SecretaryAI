"""Tests for booking-related live templates and their booking_search flag."""

from secretary_ai.core.config import Settings
from secretary_ai.services.live_templates import LiveTemplateMatcher


def test_restaurant_template(tmp_path) -> None:
    matcher = LiveTemplateMatcher(
        Settings(agent_live_template_path=str(tmp_path / "t.json"), language="en")
    )
    hit = matcher.match("find a restaurant near me")
    assert hit is not None
    assert hit["id"] == "booking_restaurant"
    assert hit["booking_search"] == "find_restaurant"


def test_hotel_template(tmp_path) -> None:
    matcher = LiveTemplateMatcher(
        Settings(agent_live_template_path=str(tmp_path / "t.json"), language="en")
    )
    hit = matcher.match("find a hotel in Paris")
    assert hit is not None
    assert hit["id"] == "booking_hotel"
    assert hit["booking_search"] == "find_hotel"


def test_event_template(tmp_path) -> None:
    matcher = LiveTemplateMatcher(
        Settings(agent_live_template_path=str(tmp_path / "t.json"), language="en")
    )
    hit = matcher.match("find tickets for tonight")
    assert hit is not None
    assert hit["id"] == "booking_event"
    assert hit["booking_search"] == "find_event"


def test_travel_template(tmp_path) -> None:
    matcher = LiveTemplateMatcher(
        Settings(agent_live_template_path=str(tmp_path / "t.json"), language="en")
    )
    hit = matcher.match("find a flight to Barcelona")
    assert hit is not None
    assert hit["id"] == "booking_travel"
    assert hit["booking_search"] == "find_travel"


def test_evening_template(tmp_path) -> None:
    matcher = LiveTemplateMatcher(
        Settings(agent_live_template_path=str(tmp_path / "t.json"), language="en")
    )
    hit = matcher.match("plan an evening out")
    assert hit is not None
    assert hit["id"] == "booking_evening"
    assert hit["booking_search"] == "plan_evening"


def test_non_booking_template_has_empty_booking_search(tmp_path) -> None:
    matcher = LiveTemplateMatcher(
        Settings(agent_live_template_path=str(tmp_path / "t.json"), language="en")
    )
    hit = matcher.match("hello there")
    assert hit is not None
    assert hit["booking_search"] == ""
