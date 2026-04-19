import asyncio
from secretary_ai.core.config import Settings
from secretary_ai.services.tavily_search import tavily_search

_RESTAURANT_DOMAINS = ["opentable.com", "timeout.com", "resy.com", "tripadvisor.com"]
_HOTEL_DOMAINS = ["booking.com", "hotels.com", "airbnb.com", "expedia.com"]
_EVENT_DOMAINS = ["ticketmaster.com", "seetickets.com", "timeout.com", "eventbrite.com"]
_FLIGHT_DOMAINS = ["skyscanner.net", "kayak.com", "google.com"]
_TRAIN_DOMAINS = ["nationalrail.co.uk", "trainline.com", "raileurope.com"]
_BUS_DOMAINS = ["nationalexpress.com", "megabus.com", "flixbus.com"]

class BookingService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def search_restaurants(self, location: str, cuisine: str | None = None, price_range: str | None = None) -> list[dict]:
        parts = ["best"]
        if cuisine:
            parts.append(cuisine)
        parts.append("restaurants in")
        parts.append(location)
        if price_range:
            parts.append(price_range)
        return await tavily_search(self.settings, " ".join(parts), max_results=5, include_domains=_RESTAURANT_DOMAINS)

    async def search_hotels(self, location: str, check_in: str, check_out: str, budget: str | None = None) -> list[dict]:
        parts = [f"hotels in {location} {check_in} to {check_out}"]
        if budget:
            parts.append(budget)
        return await tavily_search(self.settings, " ".join(parts), max_results=5, include_domains=_HOTEL_DOMAINS)

    async def search_events(self, location: str, event_type: str, date: str | None = None) -> list[dict]:
        parts = [event_type, "in", location]
        if date:
            parts.append(date)
        return await tavily_search(self.settings, " ".join(parts), max_results=5, include_domains=_EVENT_DOMAINS)

    async def search_travel(self, origin: str, destination: str, date: str, mode: str, return_date: str | None = None) -> list[dict]:
        mode_l = (mode or "").lower()
        if mode_l == "train":
            domains = _TRAIN_DOMAINS
        elif mode_l == "bus":
            domains = _BUS_DOMAINS
        else:
            domains = _FLIGHT_DOMAINS
        q = f"{mode} from {origin} to {destination} on {date}"
        if return_date:
            q += f" return {return_date}"
        return await tavily_search(self.settings, q, max_results=5, include_domains=domains)

    async def plan_evening(self, location: str, date: str, preferences: str | None = None) -> dict[str, list[dict]]:
        pref = preferences or ""
        dinner_q = f"dinner restaurants in {location} {date} {pref}".strip()
        ent_q = f"theatre concerts bars in {location} {date} {pref}".strip()
        dinner, entertainment = await asyncio.gather(
            tavily_search(self.settings, dinner_q, max_results=3, include_domains=_RESTAURANT_DOMAINS),
            tavily_search(self.settings, ent_q, max_results=3, include_domains=_EVENT_DOMAINS),
        )
        return {"dinner": dinner, "entertainment": entertainment}
