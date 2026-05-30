"""Tests for the booking search service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from secretary_ai.core.config import Settings
from secretary_ai.services.booking import BookingService, _voice_summary


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        booking_default_location="London",
        booking_max_results=3,
    )


@pytest.fixture()
def service(settings: Settings) -> BookingService:
    return BookingService(settings)


# --- _voice_summary unit tests ---


def test_voice_summary_with_results() -> None:
    results = [
        {"title": "Alpha Place", "url": "http://a.com"},
        {"title": "Beta House", "url": "http://b.com"},
        {"title": "Gamma Spot", "url": "http://c.com"},
    ]
    summary = _voice_summary(results, "restaurants")
    assert "Alpha Place" in summary
    assert "Beta House" in summary
    assert "Gamma Spot" in summary


def test_voice_summary_single_result() -> None:
    results = [{"title": "Only Place", "url": "http://a.com"}]
    summary = _voice_summary(results, "hotels")
    assert "Only Place" in summary
    assert "one option" in summary.lower()


def test_voice_summary_empty() -> None:
    summary = _voice_summary([], "events")
    assert "couldn't find" in summary.lower()


def test_voice_summary_skips_error_entries() -> None:
    results = [
        {"title": "Good Place", "url": "http://a.com"},
        {"title": "Bad Place", "url": "http://b.com", "error": "timeout"},
    ]
    summary = _voice_summary(results, "restaurants")
    assert "Good Place" in summary
    assert "one option" in summary.lower()


# --- BookingService search methods ---

MOCK_RESULTS: list[dict[str, Any]] = [
    {"title": "Test Result 1", "url": "http://test1.com", "content": "Great place", "score": 0.9},
    {"title": "Test Result 2", "url": "http://test2.com", "content": "Nice spot", "score": 0.8},
]


@pytest.mark.asyncio()
async def test_search_restaurants(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_restaurants(location="Paris", cuisine="Italian")
        assert result["category"] == "restaurants"
        assert result["location"] == "Paris"
        assert len(result["results"]) == 2
        assert "voice_summary" in result
        assert service.last_results["restaurants"] == MOCK_RESULTS


@pytest.mark.asyncio()
async def test_search_restaurants_default_location(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_restaurants()
        assert result["location"] == "London"


@pytest.mark.asyncio()
async def test_search_hotels(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_hotels(location="Rome", check_in="2025-01-01", check_out="2025-01-05")
        assert result["category"] == "hotels"
        assert result["location"] == "Rome"
        assert len(result["results"]) == 2


@pytest.mark.asyncio()
async def test_search_events(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_events(event_type="concerts", date="tonight")
        assert result["category"] == "events"
        assert len(result["results"]) == 2


@pytest.mark.asyncio()
async def test_search_travel_flight(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_travel(origin="London", destination="NYC", mode="flight")
        assert result["category"] == "travel"
        assert result["mode"] == "flight"


@pytest.mark.asyncio()
async def test_search_travel_train(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_travel(destination="Edinburgh", mode="train")
        assert result["mode"] == "train"


@pytest.mark.asyncio()
async def test_plan_evening(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.plan_evening(location="Manchester")
        assert result["category"] == "evening_plan"
        assert "dinner" in result
        assert "entertainment" in result
        assert "voice_summary" in result


@pytest.mark.asyncio()
async def test_search_by_action_restaurant(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_by_action("find_restaurant", "Italian food")
        assert result["category"] == "restaurants"


@pytest.mark.asyncio()
async def test_search_by_action_hotel(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_by_action("find_hotel", "near airport")
        assert result["category"] == "hotels"


@pytest.mark.asyncio()
async def test_search_by_action_event(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_by_action("find_event", "jazz concerts")
        assert result["category"] == "events"


@pytest.mark.asyncio()
async def test_search_by_action_travel(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_by_action("find_travel", "train to Edinburgh")
        assert result["category"] == "travel"
        assert result["mode"] == "train"


@pytest.mark.asyncio()
async def test_search_by_action_evening(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_by_action("plan_evening", "fun night")
        assert result["category"] == "evening_plan"


@pytest.mark.asyncio()
async def test_search_by_action_unknown(service: BookingService) -> None:
    result = await service.search_by_action("unknown_action", "something")
    assert result["category"] == "unknown"
    assert "not sure" in result["voice_summary"].lower()


@pytest.mark.asyncio()
async def test_search_by_action_with_extracted_fields(service: BookingService) -> None:
    with patch("secretary_ai.services.booking.tavily_search", new_callable=AsyncMock, return_value=MOCK_RESULTS):
        result = await service.search_by_action(
            "find_restaurant",
            "",
            extracted={"location": "Tokyo", "cuisine": "Sushi"},
        )
        assert result["location"] == "Tokyo"


def test_last_results_initially_empty(service: BookingService) -> None:
    assert service.last_results == {}
