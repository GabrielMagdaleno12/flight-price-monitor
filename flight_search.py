from datetime import date, timedelta
from typing import Iterator, Optional

from fast_flights import FlightQuery, Passengers, create_query, get_flights


def _parse_price(price_str: str) -> Optional[float]:
    """Convert a price string like '$1,234.56' or 'R$ 1.234,56' into a float."""
    digits = "".join(ch for ch in price_str if ch.isdigit() or ch in ".,")
    if not digits:
        return None

    if "," in digits and "." in digits:
        if digits.rfind(",") > digits.rfind("."):
            # comma is the decimal separator; dot(s) are thousands separators
            digits = digits.replace(".", "").replace(",", ".")
        else:
            # dot is the decimal separator; comma(s) are thousands separators
            digits = digits.replace(",", "")
    elif "," in digits:
        digits = digits.replace(",", "")

    try:
        return float(digits)
    except ValueError:
        return None


def search_round_trip(from_airport: str, to_airport: str, depart_date: str, return_date: str) -> Optional[float]:
    """Query Google Flights for a round trip and return the cheapest price found, or None."""
    query = create_query(
        flights=[
            FlightQuery(date=depart_date, from_airport=from_airport, to_airport=to_airport),
            FlightQuery(date=return_date, from_airport=to_airport, to_airport=from_airport),
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=1, children=0, infants_in_seat=0, infants_on_lap=0),
        currency="BRL",
    )

    try:
        result = get_flights(query)
    except Exception:
        # A single failed search (network timeout/reset, Google returning an
        # error page that fast_flights surfaces as FlightsNotFound, or a
        # parsing failure inside fast_flights itself e.g. from a DOM/JSON
        # shape change) must not crash the caller. Treat it as "no price
        # found for this one origin/date combo" so
        # find_cheapest_for_destination's per-combo loop can keep trying the
        # remaining combos instead of the whole destination being abandoned.
        # Scoped tightly to the get_flights() call itself -- a bug in our
        # own _parse_price/min() logic below is NOT swallowed here.
        return None

    prices = [p for p in (_parse_price(str(flight.price)) for flight in result) if p is not None]
    if not prices:
        return None
    return min(prices)


def iterate_flexible_dates(
    window_start: str, window_end: str, trip_length_days: int, granularity_days: int
) -> Iterator[tuple]:
    """Yield (depart_date, return_date) ISO date string pairs stepping through the window."""
    start = date.fromisoformat(window_start)
    end = date.fromisoformat(window_end)

    current = start
    while current <= end:
        depart = current.isoformat()
        return_date = (current + timedelta(days=trip_length_days)).isoformat()
        yield depart, return_date
        current += timedelta(days=granularity_days)


def find_cheapest_for_destination(
    origin_airports: list,
    to_airport: str,
    dates_config: dict,
    search_fn=search_round_trip,
) -> Optional[dict]:
    """Search every origin airport (and every date step in flexible mode) for
    `to_airport`, returning the single cheapest result or None if every
    search came back empty."""
    if dates_config["mode"] == "fixed":
        date_pairs = [(dates_config["depart_date"], dates_config["return_date"])]
    else:
        date_pairs = list(
            iterate_flexible_dates(
                dates_config["window_start"],
                dates_config["window_end"],
                dates_config["trip_length_days"],
                dates_config["granularity_days"],
            )
        )

    best = None
    for origin in origin_airports:
        for depart_date, return_date in date_pairs:
            price = search_fn(origin, to_airport, depart_date, return_date)
            if price is None:
                continue
            if best is None or price < best["price"]:
                best = {"price": price, "depart_date": depart_date, "return_date": return_date}

    return best
