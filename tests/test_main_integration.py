# tests/test_main_integration.py
"""End-to-end test of main() itself: config loading -> search -> alert ->
notify -> history save. Everything else (process_destinations, individual
notifiers, flight_search internals) is already covered elsewhere -- this
just closes the gap that main() itself was never exercised."""
import json

import main

CONFIG_YAML = """
origin: [GRU]

destinations:
  - country: "Portugal"
    airport: "LIS"

dates:
  mode: fixed
  depart_date: "2026-11-10"
  return_date: "2026-11-24"

alerts:
  price_ceiling_brl: 3500
  drop_pct_threshold: 15

notifications:
  telegram: true
  discord: false
  email: false
"""


def test_main_end_to_end_writes_history_and_sends_alert(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML, encoding="utf-8")
    history_path = tmp_path / "data" / "price_history.json"

    monkeypatch.setattr(main, "CONFIG_FILE", config_path)
    monkeypatch.setattr(main, "HISTORY_FILE", history_path)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat-id")

    sent_messages = []

    def fake_send_telegram(token, chat_id, message):
        sent_messages.append(message)
        return True

    monkeypatch.setattr(main, "send_telegram", fake_send_telegram)
    monkeypatch.setattr(main, "search_round_trip", lambda *args, **kwargs: 3000.0)

    main.main()

    assert len(sent_messages) == 1
    assert "Portugal" in sent_messages[0]

    assert history_path.exists()
    saved = json.loads(history_path.read_text(encoding="utf-8"))
    entry = saved["LIS|2026-11-10|2026-11-24"]
    assert entry["destination"] == "Portugal"
    assert entry["lowest_price_brl"] == 3000.0
    assert entry["last_price_brl"] == 3000.0
    assert entry["last_alerted_price"] == 3000.0
