# tests/test_price_store.py
from price_store import load_history, make_key, save_history, update_entry


def test_load_history_returns_empty_dict_when_file_missing(tmp_path):
    assert load_history(tmp_path / "missing.json") == {}


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "history.json"
    save_history(path, {"LIS|2026-11-10|2026-11-24": {"lowest_price_brl": 3000.0}})

    loaded = load_history(path)

    assert loaded == {"LIS|2026-11-10|2026-11-24": {"lowest_price_brl": 3000.0}}


def test_make_key_joins_airport_and_dates_with_pipe():
    assert make_key("LIS", "2026-11-10", "2026-11-24") == "LIS|2026-11-10|2026-11-24"


def test_update_entry_creates_new_record_when_key_absent():
    history = {}

    result = update_entry(history, "LIS|2026-11-10|2026-11-24", "Portugal", 3000.0, "2026-09-10T08:00:00Z")

    entry = result["LIS|2026-11-10|2026-11-24"]
    assert entry["destination"] == "Portugal"
    assert entry["lowest_price_brl"] == 3000.0
    assert entry["last_price_brl"] == 3000.0
    assert entry["first_seen"] == "2026-09-10T08:00:00Z"
    assert entry["last_checked"] == "2026-09-10T08:00:00Z"


def test_update_entry_keeps_lower_of_old_and_new_as_lowest():
    history = {
        "LIS|2026-11-10|2026-11-24": {
            "destination": "Portugal",
            "lowest_price_brl": 2800.0,
            "last_price_brl": 2800.0,
            "first_seen": "2026-09-01T00:00:00Z",
            "last_checked": "2026-09-01T00:00:00Z",
        }
    }

    result = update_entry(history, "LIS|2026-11-10|2026-11-24", "Portugal", 3200.0, "2026-09-10T08:00:00Z")

    entry = result["LIS|2026-11-10|2026-11-24"]
    assert entry["lowest_price_brl"] == 2800.0
    assert entry["last_price_brl"] == 3200.0
    assert entry["first_seen"] == "2026-09-01T00:00:00Z"
    assert entry["last_checked"] == "2026-09-10T08:00:00Z"


def test_update_entry_does_not_mutate_input_history(tmp_path):
    history = {}
    result = update_entry(history, "LIS|2026-11-10|2026-11-24", "Portugal", 3000.0, "2026-09-10T08:00:00Z")
    assert history == {}
    assert result != {}


def test_update_entry_sets_last_alerted_price_none_when_not_given_for_new_entry():
    result = update_entry({}, "LIS|2026-11-10|2026-11-24", "Portugal", 3000.0, "2026-09-10T08:00:00Z")

    assert result["LIS|2026-11-10|2026-11-24"]["last_alerted_price"] is None


def test_update_entry_stores_alerted_price_when_given_for_new_entry():
    result = update_entry(
        {}, "LIS|2026-11-10|2026-11-24", "Portugal", 3000.0, "2026-09-10T08:00:00Z", alerted_price=3000.0
    )

    assert result["LIS|2026-11-10|2026-11-24"]["last_alerted_price"] == 3000.0


def test_update_entry_preserves_last_alerted_price_when_alerted_price_not_given():
    history = {
        "LIS|2026-11-10|2026-11-24": {
            "destination": "Portugal",
            "lowest_price_brl": 3000.0,
            "last_price_brl": 3000.0,
            "last_alerted_price": 3000.0,
            "first_seen": "2026-09-01T00:00:00Z",
            "last_checked": "2026-09-01T00:00:00Z",
        }
    }

    result = update_entry(history, "LIS|2026-11-10|2026-11-24", "Portugal", 3100.0, "2026-09-10T09:00:00Z")

    assert result["LIS|2026-11-10|2026-11-24"]["last_alerted_price"] == 3000.0


def test_update_entry_overwrites_last_alerted_price_when_new_alerted_price_given():
    history = {
        "LIS|2026-11-10|2026-11-24": {
            "destination": "Portugal",
            "lowest_price_brl": 3000.0,
            "last_price_brl": 3000.0,
            "last_alerted_price": 3000.0,
            "first_seen": "2026-09-01T00:00:00Z",
            "last_checked": "2026-09-01T00:00:00Z",
        }
    }

    result = update_entry(
        history, "LIS|2026-11-10|2026-11-24", "Portugal", 2800.0, "2026-09-10T09:00:00Z", alerted_price=2800.0
    )

    assert result["LIS|2026-11-10|2026-11-24"]["last_alerted_price"] == 2800.0
