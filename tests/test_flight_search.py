from unittest.mock import Mock, patch

import pytest
from fast_flights.exceptions import FlightsNotFound

from flight_search import (
    MIN_PLAUSIBLE_PRICE_BRL,
    _parse_price,
    find_cheapest_for_destination,
    iterate_flexible_dates,
    search_round_trip,
)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # find_cheapest_for_destination now sleeps SEARCH_DELAY_SECONDS between
    # calls; keep the test suite fast and deterministic.
    monkeypatch.setattr("flight_search.time.sleep", lambda *_: None)


def test_parse_price_handles_dollar_sign_and_comma_thousands():
    assert _parse_price("$1,234.56") == 1234.56


def test_parse_price_handles_brl_style_dot_thousands_comma_decimal():
    assert _parse_price("R$ 1.234,56") == 1234.56


def test_parse_price_handles_single_dot_as_thousands_separator():
    assert _parse_price("R$ 1.234") == 1234.0


def test_parse_price_handles_single_comma_as_decimal_separator():
    assert _parse_price("R$ 12,50") == 12.50


def test_parse_price_returns_none_for_unparseable_string():
    assert _parse_price("indisponível") is None


# NOTE: the real fast_flights.get_flights() (v3.1.0) returns a `ResultList`,
# which *is* a list of flight objects directly (not an object with a
# `.flights` attribute), and each flight's `.price` is already a number.
# The mocks below reflect that real shape.
@patch("flight_search.get_flights")
def test_search_round_trip_returns_min_price_from_result_flights(mock_get_flights):
    mock_get_flights.return_value = [Mock(price=800), Mock(price=650)]

    price = search_round_trip("GRU", "LIS", "2026-11-10", "2026-11-24")

    assert price == 650.0


@patch("flight_search.get_flights")
def test_search_round_trip_returns_none_when_no_parseable_prices(mock_get_flights):
    mock_get_flights.return_value = [Mock(price="indisponível")]

    assert search_round_trip("GRU", "LIS", "2026-11-10", "2026-11-24") is None


@patch("flight_search.get_flights")
def test_search_round_trip_returns_none_when_price_below_plausible_floor(mock_get_flights):
    mock_get_flights.return_value = [Mock(price=MIN_PLAUSIBLE_PRICE_BRL - 1)]

    assert search_round_trip("GRU", "LIS", "2026-11-10", "2026-11-24") is None


@pytest.mark.parametrize(
    "raised_exception",
    [
        FlightsNotFound("no flights found; received error"),
        RuntimeError("connection reset"),
    ],
)
@patch("flight_search.get_flights")
def test_search_round_trip_returns_none_when_get_flights_raises(mock_get_flights, raised_exception):
    mock_get_flights.side_effect = raised_exception

    assert search_round_trip("GRU", "LIS", "2026-11-10", "2026-11-24") is None


def test_iterate_flexible_dates_steps_through_window():
    pairs = list(iterate_flexible_dates("2026-11-01", "2026-11-15", trip_length_days=14, granularity_days=7))

    assert pairs == [
        ("2026-11-01", "2026-11-15"),
        ("2026-11-08", "2026-11-22"),
        ("2026-11-15", "2026-11-29"),
    ]


def test_iterate_flexible_dates_rejects_non_positive_granularity():
    with pytest.raises(ValueError):
        list(iterate_flexible_dates("2026-11-01", "2026-11-15", trip_length_days=14, granularity_days=0))


def test_find_cheapest_for_destination_fixed_mode_single_search():
    calls = []

    def fake_search(origin, to_airport, depart_date, return_date):
        calls.append((origin, to_airport, depart_date, return_date))
        return 3000.0

    dates_config = {"mode": "fixed", "depart_date": "2026-11-10", "return_date": "2026-11-24"}

    result = find_cheapest_for_destination(["GRU"], "LIS", dates_config, search_fn=fake_search)

    assert result == {
        "price": 3000.0,
        "depart_date": "2026-11-10",
        "return_date": "2026-11-24",
        "origin": "GRU",
    }
    assert calls == [("GRU", "LIS", "2026-11-10", "2026-11-24")]


def test_find_cheapest_for_destination_flexible_mode_picks_lowest():
    prices_by_date = {"2026-11-01": 3200.0, "2026-11-08": 2900.0, "2026-11-15": 3100.0}

    def fake_search(origin, to_airport, depart_date, return_date):
        return prices_by_date[depart_date]

    dates_config = {
        "mode": "flexible",
        "window_start": "2026-11-01",
        "window_end": "2026-11-15",
        "trip_length_days": 14,
        "granularity_days": 7,
    }

    result = find_cheapest_for_destination(["GRU"], "LIS", dates_config, search_fn=fake_search)

    assert result == {
        "price": 2900.0,
        "depart_date": "2026-11-08",
        "return_date": "2026-11-22",
        "origin": "GRU",
    }


def test_find_cheapest_for_destination_tries_every_origin_airport():
    prices_by_origin = {"GRU": 3200.0, "CGH": 2950.0}

    def fake_search(origin, to_airport, depart_date, return_date):
        return prices_by_origin[origin]

    dates_config = {"mode": "fixed", "depart_date": "2026-11-10", "return_date": "2026-11-24"}

    result = find_cheapest_for_destination(["GRU", "CGH"], "LIS", dates_config, search_fn=fake_search)

    assert result["price"] == 2950.0
    assert result["origin"] == "CGH"


def test_find_cheapest_for_destination_returns_none_when_every_search_fails():
    result = find_cheapest_for_destination(
        ["GRU"],
        "LIS",
        {"mode": "fixed", "depart_date": "2026-11-10", "return_date": "2026-11-24"},
        search_fn=lambda *a: None,
    )

    assert result is None
