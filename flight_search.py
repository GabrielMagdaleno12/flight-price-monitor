import time
from datetime import date, timedelta
from typing import Iterator, Optional

from fast_flights import FlightQuery, Passengers, create_query, get_flights

# Any "price" below this is implausible for an international round trip out of
# São Paulo and is far more likely to be a wrong-currency or garbage value. We
# refuse it instead of letting it be baked into `lowest_price_brl` forever
# (that field only ever decreases, so a bad low value has no repair path).
MIN_PLAUSIBLE_PRICE_BRL = 100.0

# Delay between individual Google Flights requests, to avoid hammering the
# endpoint from a single runner IP.
SEARCH_DELAY_SECONDS = 1.0


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
    elif "," in digits or "." in digits:
        # Exactly one kind of separator: decide by how many digits follow the
        # last one. Three digits after it means a thousands separator
        # ("1.234" -> 1234.0); one or two mean a decimal separator
        # ("12,50" -> 12.5). More than one occurrence can only be thousands.
        separator = "," if "," in digits else "."
        if digits.count(separator) > 1 or len(digits) - digits.rfind(separator) - 1 == 3:
            digits = digits.replace(separator, "")
        else:
            digits = digits.replace(separator, ".")

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

    cheapest = min(prices)
    if cheapest < MIN_PLAUSIBLE_PRICE_BRL:
        # Implausibly low price (wrong currency, garbage scrape, etc.) -- treat
        # as no valid result rather than poisoning lowest_price_brl forever.
        return None
    return cheapest


def iterate_flexible_dates(
    window_start: str, window_end: str, trip_length_days: int, granularity_days: int
) -> Iterator[tuple]:
    """Yield (depart_date, return_date) ISO date string pairs stepping through the window."""
    if granularity_days < 1:
        raise ValueError("granularity_days must be >= 1 (0 or negative would loop forever)")

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
    calls_made = 0
    for origin in origin_airports:
        for depart_date, return_date in date_pairs:
            if calls_made > 0:
                time.sleep(SEARCH_DELAY_SECONDS)
            price = search_fn(origin, to_airport, depart_date, return_date)
            calls_made += 1
            if price is None:
                continue
            if best is None or price < best["price"]:
                best = {
                    "price": price,
                    "depart_date": depart_date,
                    "return_date": return_date,
                    "origin": origin,
                }

    return best
