"""Booking search service — restaurants, hotels, events, travel, evening plans.

Wraps Tavily web search with domain-specific filters and returns both
raw results and voice-ready summaries for the live call pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from secretary_ai.core.config import Settings
from secretary_ai.services.tavily_search import tavily_search

logger = logging.getLogger(__name__)

_RESTAURANT_DOMAINS = ["opentable.com", "timeout.com", "resy.com", "tripadvisor.com"]
_HOTEL_DOMAINS = ["booking.com", "hotels.com", "airbnb.com", "expedia.com"]
_EVENT_DOMAINS = ["ticketmaster.com", "seetickets.com", "timeout.com", "eventbrite.com"]
_FLIGHT_DOMAINS = ["skyscanner.net", "kayak.com", "google.com"]
_TRAIN_DOMAINS = ["nationalrail.co.uk", "trainline.com", "raileurope.com"]
_BUS_DOMAINS = ["nationalexpress.com", "megabus.com", "flixbus.com"]


def _voice_summary(results: list[dict[str, Any]], category: str) -> str:
    """Build a short voice-friendly summary from search results."""
    valid = [r for r in results if r.get("title") and not r.get("error")]
    if not valid:
        return f"I couldn't find any {category} right now. Please try again later."
    names = [str(r["title"]).strip() for r in valid[:3]]
    if len(names) == 1:
        return f"I found one option: {names[0]}."
    listing = ", ".join(names[:-1]) + (" and " if len(names) == 2 else ", and ") + names[-1]
    return f"Here are the top results: {listing}."


class BookingService:
    """Search for restaurants, hotels, events, and travel options."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._last_results: dict[str, list[dict[str, Any]]] = {}

    @property
    def last_results(self) -> dict[str, list[dict[str, Any]]]:
        """Most recent search results keyed by category."""
        return self._last_results

    async def search_restaurants(
        self,
        location: str | None = None,
        cuisine: str | None = None,
        price_range: str | None = None,
    ) -> dict[str, Any]:
        loc = location or self.settings.booking_default_location
        parts = ["best"]
        if cuisine:
            parts.append(cuisine)
        parts.extend(["restaurants in", loc])
        if price_range:
            parts.append(price_range)
        results = await tavily_search(
            self.settings,
            " ".join(parts),
            max_results=self.settings.booking_max_results,
            include_domains=_RESTAURANT_DOMAINS,
        )
        self._last_results["restaurants"] = results
        return {
            "category": "restaurants",
            "location": loc,
            "results": results,
            "voice_summary": _voice_summary(results, "restaurants"),
        }

    async def search_hotels(
        self,
        location: str | None = None,
        check_in: str | None = None,
        check_out: str | None = None,
        budget: str | None = None,
    ) -> dict[str, Any]:
        loc = location or self.settings.booking_default_location
        dates = f"{check_in or 'soon'} to {check_out or 'flexible'}"
        parts = [f"hotels in {loc} {dates}"]
        if budget:
            parts.append(budget)
        results = await tavily_search(
            self.settings,
            " ".join(parts),
            max_results=self.settings.booking_max_results,
            include_domains=_HOTEL_DOMAINS,
        )
        self._last_results["hotels"] = results
        return {
            "category": "hotels",
            "location": loc,
            "results": results,
            "voice_summary": _voice_summary(results, "hotels"),
        }

    async def search_events(
        self,
        location: str | None = None,
        event_type: str = "events",
        date: str | None = None,
    ) -> dict[str, Any]:
        loc = location or self.settings.booking_default_location
        parts = [event_type, "in", loc]
        if date:
            parts.append(date)
        results = await tavily_search(
            self.settings,
            " ".join(parts),
            max_results=self.settings.booking_max_results,
            include_domains=_EVENT_DOMAINS,
        )
        self._last_results["events"] = results
        return {
            "category": "events",
            "location": loc,
            "results": results,
            "voice_summary": _voice_summary(results, "events"),
        }

    async def search_travel(
        self,
        origin: str | None = None,
        destination: str | None = None,
        date: str = "soon",
        mode: str = "flight",
        return_date: str | None = None,
    ) -> dict[str, Any]:
        orig = origin or self.settings.booking_default_location
        dest = destination or ""
        mode_l = (mode or "flight").lower()
        if mode_l == "train":
            domains = _TRAIN_DOMAINS
        elif mode_l == "bus":
            domains = _BUS_DOMAINS
        else:
            domains = _FLIGHT_DOMAINS
        if dest:
            q = f"{mode} from {orig} to {dest} on {date}"
        else:
            q = f"{mode} from {orig} on {date}"
        if return_date:
            q += f" return {return_date}"
        results = await tavily_search(
            self.settings,
            q,
            max_results=self.settings.booking_max_results,
            include_domains=domains,
        )
        self._last_results["travel"] = results
        return {
            "category": "travel",
            "mode": mode_l,
            "origin": orig,
            "destination": dest,
            "results": results,
            "voice_summary": _voice_summary(results, f"{mode_l} options"),
        }

    async def plan_evening(
        self,
        location: str | None = None,
        date: str = "tonight",
        preferences: str | None = None,
    ) -> dict[str, Any]:
        loc = location or self.settings.booking_default_location
        pref = preferences or ""
        dinner_q = f"dinner restaurants in {loc} {date} {pref}".strip()
        ent_q = f"theatre concerts bars in {loc} {date} {pref}".strip()
        dinner, entertainment = await asyncio.gather(
            tavily_search(self.settings, dinner_q, max_results=3, include_domains=_RESTAURANT_DOMAINS),
            tavily_search(self.settings, ent_q, max_results=3, include_domains=_EVENT_DOMAINS),
        )
        self._last_results["evening_dinner"] = dinner
        self._last_results["evening_entertainment"] = entertainment

        dinner_summary = _voice_summary(dinner, "dinner spots")
        ent_summary = _voice_summary(entertainment, "entertainment options")
        return {
            "category": "evening_plan",
            "location": loc,
            "results": dinner + entertainment,
            "dinner": {"results": dinner, "voice_summary": dinner_summary},
            "entertainment": {"results": entertainment, "voice_summary": ent_summary},
            "voice_summary": f"For dinner: {dinner_summary} For entertainment: {ent_summary}",
        }

    async def search_by_action(
        self,
        action: str,
        payload: str,
        extracted: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a booking search based on wake-word action type."""
        fields = extracted or {}
        location = str(fields.get("location") or "").strip() or None

        if action == "find_restaurant":
            cuisine = str(fields.get("cuisine") or "").strip() or None
            if not cuisine and payload:
                cuisine = payload
            return await self.search_restaurants(location=location, cuisine=cuisine)

        if action == "find_hotel":
            check_in = str(fields.get("check_in") or "").strip() or None
            check_out = str(fields.get("check_out") or "").strip() or None
            return await self.search_hotels(location=location, check_in=check_in, check_out=check_out)

        if action == "find_event":
            event_type = payload or "events"
            date = str(fields.get("date") or "").strip() or None
            return await self.search_events(location=location, event_type=event_type, date=date)

        if action == "find_travel":
            origin = str(fields.get("origin") or "").strip() or None
            destination = str(fields.get("destination") or "").strip() or None
            if not destination and payload:
                destination = payload
            mode = str(fields.get("mode") or "flight").strip()
            for m in ("train", "bus", "flight"):
                if m in (payload or "").lower():
                    mode = m
                    break
            return await self.search_travel(origin=origin, destination=destination, mode=mode)

        if action == "plan_evening":
            return await self.plan_evening(location=location, preferences=payload or None)

        return {"category": "unknown", "results": [], "voice_summary": "I'm not sure what to search for."}
