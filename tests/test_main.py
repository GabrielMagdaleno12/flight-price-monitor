# tests/test_main.py
from main import process_destinations


FIXED_DATES = {"mode": "fixed", "depart_date": "2026-11-10", "return_date": "2026-11-24"}


def make_destination(country="Portugal", airport="LIS", price_ceiling_brl=None):
    dest = {"country": country, "airport": airport}
    if price_ceiling_brl is not None:
        dest["price_ceiling_brl"] = price_ceiling_brl
    return dest


def test_alerts_when_price_at_or_below_ceiling():
    sent = []

    new_history = process_destinations(
        destinations=[make_destination()],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 3500.0, "drop_pct_threshold": 15},
        history={},
        search_fn=lambda *a: 3000.0,
        notify_fns=[sent.append],
        now_fn=lambda: "2026-09-10T08:00:00Z",
    )

    assert len(sent) == 1
    assert "Portugal" in sent[0]
    assert "GRU" in sent[0]
    assert new_history["LIS|2026-11-10|2026-11-24"]["lowest_price_brl"] == 3000.0
    assert new_history["LIS|2026-11-10|2026-11-24"]["last_alerted_price"] == 3000.0


def test_no_alert_when_price_above_ceiling_and_no_history():
    sent = []

    process_destinations(
        destinations=[make_destination()],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 3500.0, "drop_pct_threshold": 15},
        history={},
        search_fn=lambda *a: 4000.0,
        notify_fns=[sent.append],
        now_fn=lambda: "2026-09-10T08:00:00Z",
    )

    assert sent == []


def test_alerts_on_drop_percentage_using_recorded_history():
    sent = []
    history = {"LIS|2026-11-10|2026-11-24": {"destination": "Portugal", "lowest_price_brl": 4000.0,
                                              "last_price_brl": 4000.0, "first_seen": "x", "last_checked": "x"}}

    process_destinations(
        destinations=[make_destination(price_ceiling_brl=1000.0)],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 1000.0, "drop_pct_threshold": 15},
        history=history,
        search_fn=lambda *a: 3200.0,  # 20% drop from 4000, clears 15% threshold
        notify_fns=[sent.append],
        now_fn=lambda: "2026-09-10T08:00:00Z",
    )

    assert len(sent) == 1
    # The alert fired on the drop-% condition, not the ceiling (3200 > 1000
    # ceiling), so the message must not claim it's under the ceiling.
    assert "teto" not in sent[0]


def test_destination_level_ceiling_overrides_global_default():
    sent = []

    process_destinations(
        destinations=[make_destination(price_ceiling_brl=5000.0)],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 1000.0, "drop_pct_threshold": None},
        history={},
        search_fn=lambda *a: 4500.0,
        notify_fns=[sent.append],
        now_fn=lambda: "2026-09-10T08:00:00Z",
    )

    assert len(sent) == 1


def test_continues_and_updates_no_history_when_search_raises():
    sent = []

    def failing_search(*args):
        raise RuntimeError("boom")

    new_history = process_destinations(
        destinations=[make_destination()],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 3500.0, "drop_pct_threshold": 15},
        history={},
        search_fn=failing_search,
        notify_fns=[sent.append],
        now_fn=lambda: "2026-09-10T08:00:00Z",
    )

    assert sent == []
    assert new_history == {}


def test_continues_when_no_price_found():
    sent = []

    new_history = process_destinations(
        destinations=[make_destination()],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 3500.0, "drop_pct_threshold": 15},
        history={},
        search_fn=lambda *a: None,
        notify_fns=[sent.append],
        now_fn=lambda: "2026-09-10T08:00:00Z",
    )

    assert sent == []
    assert new_history == {}


def test_continues_when_one_notify_fn_raises():
    sent = []

    def failing_notify(message):
        raise RuntimeError("webhook down")

    process_destinations(
        destinations=[make_destination()],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 3500.0, "drop_pct_threshold": 15},
        history={},
        search_fn=lambda *a: 3000.0,
        notify_fns=[failing_notify, sent.append],
        now_fn=lambda: "2026-09-10T08:00:00Z",
    )

    assert len(sent) == 1


def test_does_not_realert_when_same_qualifying_price_seen_again():
    sent = []
    history = {
        "LIS|2026-11-10|2026-11-24": {
            "destination": "Portugal",
            "lowest_price_brl": 3000.0,
            "last_price_brl": 3000.0,
            "last_alerted_price": 3000.0,
            "first_seen": "x",
            "last_checked": "x",
        }
    }

    new_history = process_destinations(
        destinations=[make_destination()],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 3500.0, "drop_pct_threshold": 15},
        history=history,
        search_fn=lambda *a: 3000.0,  # same price already alerted for
        notify_fns=[sent.append],
        now_fn=lambda: "2026-09-10T09:00:00Z",
    )

    assert sent == []
    assert new_history["LIS|2026-11-10|2026-11-24"]["last_alerted_price"] == 3000.0


def test_realerts_when_qualifying_price_drops_further():
    sent = []
    history = {
        "LIS|2026-11-10|2026-11-24": {
            "destination": "Portugal",
            "lowest_price_brl": 3000.0,
            "last_price_brl": 3000.0,
            "last_alerted_price": 3000.0,
            "first_seen": "x",
            "last_checked": "x",
        }
    }

    new_history = process_destinations(
        destinations=[make_destination()],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 3500.0, "drop_pct_threshold": 15},
        history=history,
        search_fn=lambda *a: 2800.0,  # even better than the last alerted price
        notify_fns=[sent.append],
        now_fn=lambda: "2026-09-10T09:00:00Z",
    )

    assert len(sent) == 1
    assert new_history["LIS|2026-11-10|2026-11-24"]["last_alerted_price"] == 2800.0


def test_does_not_realert_when_price_no_longer_qualifies_but_updates_last_price():
    sent = []
    history = {
        "LIS|2026-11-10|2026-11-24": {
            "destination": "Portugal",
            "lowest_price_brl": 3000.0,
            "last_price_brl": 3000.0,
            "last_alerted_price": 3000.0,
            "first_seen": "x",
            "last_checked": "x",
        }
    }

    new_history = process_destinations(
        destinations=[make_destination()],
        origin_airports=["GRU"],
        dates_config=FIXED_DATES,
        alerts_config={"price_ceiling_brl": 3500.0, "drop_pct_threshold": 15},
        history=history,
        search_fn=lambda *a: 3600.0,  # above ceiling (3500) and not a 15% drop off 3000
        notify_fns=[sent.append],
        now_fn=lambda: "2026-09-10T09:00:00Z",
    )

    assert sent == []
    # No new alert was sent, so the previously recorded value is preserved.
    assert new_history["LIS|2026-11-10|2026-11-24"]["last_alerted_price"] == 3000.0
    assert new_history["LIS|2026-11-10|2026-11-24"]["last_price_brl"] == 3600.0
