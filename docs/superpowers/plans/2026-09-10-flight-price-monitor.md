# Flight Price Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub-Actions-hosted system that checks Google Flights prices every 30 minutes for a user-configured list of destinations from GRU/CGH and alerts via Telegram, Discord, and e-mail when a price is at or below a ceiling, or has dropped a meaningful percentage vs. the lowest price ever seen.

**Architecture:** A single Python script (`main.py`) run on a GitHub Actions cron reads `config.yaml`, queries Google Flights per destination via the `fast-flights` library (`flight_search.py`), compares results against a committed JSON price history (`price_store.py`) using pure alert-decision logic (`alert_engine.py`), and fires independent notifier functions (`notifiers/telegram.py`, `notifiers/discord.py`, `notifiers/email.py`). The updated history is committed back to the repo by the workflow.

**Tech Stack:** Python 3.11, `fast-flights` (unofficial Google Flights client), `PyYAML`, `requests`, `smtplib` (stdlib), `pytest` + `unittest.mock` for tests, GitHub Actions (`ubuntu-latest`).

**Spec:** `docs/superpowers/specs/2026-09-10-flight-price-monitor-design.md`

## Global Constraints

- Must run entirely on GitHub Actions free tier (public repo, `ubuntu-latest`, Python 3.11) — no paid services, no VM to maintain.
- Price source is Google Flights via the `fast-flights` library only — no browser/Playwright scraping, no specific-airline/OTA scraping (out of scope for this plan).
- Alert fires when **either** `current_price <= price_ceiling` **or** `current_price <= lowest_price_seen * (1 - drop_pct_threshold/100)` — not both required.
- Price history is keyed as `"{airport}|{depart_date}|{return_date}"` and `lowest_price_brl` in that record must only ever decrease, never increase.
- A failure on one destination, one notifier channel, or a missing secret must never stop the rest of the run — always log and continue.
- No true "anywhere" search — destinations come from a user-maintained list in `config.yaml`.

---

## File Structure

```
flight-price-monitor/
├── config.yaml                      <- user-edited config
├── data/
│   └── price_history.json           <- created on first run, committed by the workflow
├── flight_search.py                 <- fast-flights wrapper + date/origin iteration
├── price_store.py                   <- price_history.json read/write/update
├── alert_engine.py                  <- pure should_alert() decision
├── notifiers/
│   ├── __init__.py
│   ├── telegram.py
│   ├── discord.py
│   └── email.py
├── main.py                          <- orchestration + entrypoint
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── .gitignore
├── README.md
├── tests/
│   ├── test_alert_engine.py
│   ├── test_price_store.py
│   ├── test_flight_search.py
│   ├── test_notifiers.py
│   └── test_main.py
└── .github/workflows/
    └── check-flights.yml
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `config.yaml`
- Create: `README.md`

**Interfaces:**
- Produces: `config.yaml` structure that every later task's code reads — top-level keys `origin` (list[str]), `destinations` (list of `{country, airport, price_ceiling_brl?}`), `dates` (`mode`, plus `depart_date`/`return_date` or `window_start`/`window_end`/`trip_length_days`/`granularity_days`), `alerts` (`price_ceiling_brl`, `drop_pct_threshold`), `notifications` (`telegram`, `discord`, `email` booleans).

- [ ] **Step 1: Create `requirements.txt`**

```
requests>=2.31,<3
PyYAML>=6.0,<7
fast-flights>=2.2
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0,<9
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
pythonpath = .
```

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
```

- [ ] **Step 5: Create `config.yaml`**

```yaml
origin: [GRU, CGH]

destinations:
  - country: "Portugal"
    airport: "LIS"
  - country: "Itália"
    airport: "FCO"
  - country: "Japão"
    airport: "NRT"

dates:
  mode: flexible          # "fixed" or "flexible"
  # mode: fixed
  # depart_date: "2026-11-10"
  # return_date: "2026-11-24"
  window_start: "2026-11-01"
  window_end: "2027-02-28"
  trip_length_days: 14
  granularity_days: 7     # step size when scanning the flexible window

alerts:
  price_ceiling_brl: 3500        # global default; a destination can override with its own price_ceiling_brl
  drop_pct_threshold: 15         # alert when price falls at least this % below the recorded lowest

notifications:
  telegram: true
  discord: true
  email: true
```

- [ ] **Step 6: Create `README.md`**

```markdown
# Flight Price Monitor

Monitora preços de passagens aéreas partindo de São Paulo (GRU/CGH) para uma
lista de destinos que você escolhe, e avisa no Telegram, Discord e e-mail
quando encontra um preço muito bom.

## Configuração (uma vez só)

1. **Telegram**: fale com [@BotFather](https://t.me/BotFather), crie um bot
   com `/newbot` e guarde o token. Envie uma mensagem qualquer para o bot e
   depois acesse `https://api.telegram.org/bot<TOKEN>/getUpdates` para
   pegar o seu `chat_id` (campo `message.chat.id`).
2. **Discord**: nas configurações de um canal do seu servidor, vá em
   Integrações → Webhooks → Novo Webhook, e copie a URL.
3. **E-mail**: gere uma senha de app para sua conta (ex: [Gmail App
   Password](https://myaccount.google.com/apppasswords)).
4. No repositório do GitHub, vá em **Settings → Secrets and variables →
   Actions** e adicione:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `DISCORD_WEBHOOK_URL`
   - `SMTP_HOST` (ex: `smtp.gmail.com`)
   - `SMTP_PORT` (ex: `587`)
   - `SMTP_USER` (seu e-mail)
   - `SMTP_PASSWORD` (a senha de app gerada)
   - `EMAIL_TO` (e-mail que vai receber os alertas)

## Uso

Edite `config.yaml` para ajustar origem, destinos candidatos, datas (fixas
ou janela flexível) e os limites de alerta (teto de preço e % de queda).

A checagem roda automaticamente pelo GitHub Actions a cada 30 minutos (veja
`.github/workflows/check-flights.yml`). Para rodar manualmente e testar, vá
na aba **Actions** do repositório → **Check flight prices** → **Run
workflow**.

## Rodando localmente (opcional, para testes)

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Nota sobre moeda

O `fast-flights` consulta o Google Flights e o preço retornado pode vir em
USD dependendo da região consultada, não necessariamente em BRL. Na primeira
execução manual (veja o plano de testes), confira a moeda retornada e ajuste
`price_ceiling_brl` em `config.yaml` de acordo se for o caso.
```

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt pytest.ini .gitignore config.yaml README.md
git commit -m "Add project scaffolding for flight price monitor"
```

---

### Task 2: Alert decision logic

**Files:**
- Create: `alert_engine.py`
- Test: `tests/test_alert_engine.py`

**Interfaces:**
- Consumes: nothing (pure function, no dependencies on other tasks).
- Produces: `should_alert(current_price: float, price_ceiling: Optional[float], lowest_price_seen: Optional[float], drop_pct_threshold: Optional[float]) -> bool`, used by Task 6 (`main.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_alert_engine.py
from alert_engine import should_alert


def test_alerts_when_price_at_or_below_ceiling():
    assert should_alert(3000.0, price_ceiling=3500.0, lowest_price_seen=None, drop_pct_threshold=15) is True


def test_no_alert_when_price_above_ceiling_and_no_history():
    assert should_alert(4000.0, price_ceiling=3500.0, lowest_price_seen=None, drop_pct_threshold=15) is False


def test_alerts_on_drop_percentage_even_above_ceiling():
    # lowest ever seen was 4000; a 20% drop (3200) clears the 15% threshold (3400)
    assert should_alert(3200.0, price_ceiling=1000.0, lowest_price_seen=4000.0, drop_pct_threshold=15) is True


def test_no_alert_when_drop_below_threshold():
    # only a 5% drop from 4000 (3800), threshold requires 15%
    assert should_alert(3800.0, price_ceiling=1000.0, lowest_price_seen=4000.0, drop_pct_threshold=15) is False


def test_no_alert_when_no_ceiling_and_no_history():
    assert should_alert(3000.0, price_ceiling=None, lowest_price_seen=None, drop_pct_threshold=15) is False


def test_ceiling_alone_triggers_without_drop_threshold_configured():
    assert should_alert(3000.0, price_ceiling=3500.0, lowest_price_seen=None, drop_pct_threshold=None) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_alert_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alert_engine'`

- [ ] **Step 3: Write the implementation**

```python
# alert_engine.py
from typing import Optional


def should_alert(
    current_price: float,
    price_ceiling: Optional[float],
    lowest_price_seen: Optional[float],
    drop_pct_threshold: Optional[float],
) -> bool:
    if price_ceiling is not None and current_price <= price_ceiling:
        return True

    if drop_pct_threshold is not None and lowest_price_seen is not None:
        threshold_price = lowest_price_seen * (1 - drop_pct_threshold / 100)
        if current_price <= threshold_price:
            return True

    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_alert_engine.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add alert_engine.py tests/test_alert_engine.py
git commit -m "Add alert_engine.should_alert decision logic"
```

---

### Task 3: Price history store

**Files:**
- Create: `price_store.py`
- Test: `tests/test_price_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load_history(path: Path) -> dict`, `save_history(path: Path, history: dict) -> None`, `make_key(airport: str, depart_date: str, return_date: str) -> str`, `update_entry(history: dict, key: str, destination_name: str, price: float, checked_at: str) -> dict` — all used by Task 6 (`main.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_price_store.py
import json
from pathlib import Path

import pytest

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_price_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'price_store'`

- [ ] **Step 3: Write the implementation**

```python
# price_store.py
import json
from pathlib import Path


def load_history(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_history(path: Path, history: dict) -> None:
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


def make_key(airport: str, depart_date: str, return_date: str) -> str:
    return f"{airport}|{depart_date}|{return_date}"


def update_entry(history: dict, key: str, destination_name: str, price: float, checked_at: str) -> dict:
    new_history = dict(history)
    existing = new_history.get(key)

    if existing is None:
        new_history[key] = {
            "destination": destination_name,
            "lowest_price_brl": price,
            "last_price_brl": price,
            "first_seen": checked_at,
            "last_checked": checked_at,
        }
    else:
        updated = dict(existing)
        updated["lowest_price_brl"] = min(existing["lowest_price_brl"], price)
        updated["last_price_brl"] = price
        updated["last_checked"] = checked_at
        new_history[key] = updated

    return new_history
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_price_store.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add price_store.py tests/test_price_store.py
git commit -m "Add price_store for reading/writing price history"
```

---

### Task 4: Flight search (Google Flights via fast-flights)

**Files:**
- Create: `flight_search.py`
- Test: `tests/test_flight_search.py`

**Interfaces:**
- Consumes: `fast_flights.FlightData`, `fast_flights.Passengers`, `fast_flights.get_flights` (external library).
- Produces: `search_round_trip(from_airport: str, to_airport: str, depart_date: str, return_date: str) -> Optional[float]`, `iterate_flexible_dates(window_start: str, window_end: str, trip_length_days: int, granularity_days: int) -> Iterator[tuple[str, str]]`, `find_cheapest_for_destination(origin_airports: list[str], to_airport: str, dates_config: dict, search_fn=search_round_trip) -> Optional[dict]` (returns `{"price": float, "depart_date": str, "return_date": str}` or `None`) — all used by Task 6 (`main.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_flight_search.py
from unittest.mock import Mock, patch

from flight_search import (
    _parse_price,
    find_cheapest_for_destination,
    iterate_flexible_dates,
    search_round_trip,
)


def test_parse_price_handles_dollar_sign_and_comma_thousands():
    assert _parse_price("$1,234.56") == 1234.56


def test_parse_price_handles_brl_style_dot_thousands_comma_decimal():
    assert _parse_price("R$ 1.234,56") == 1234.56


def test_parse_price_returns_none_for_unparseable_string():
    assert _parse_price("indisponível") is None


@patch("flight_search.get_flights")
def test_search_round_trip_returns_min_price_from_result_flights(mock_get_flights):
    mock_get_flights.return_value = Mock(flights=[Mock(price="$800"), Mock(price="$650")])

    price = search_round_trip("GRU", "LIS", "2026-11-10", "2026-11-24")

    assert price == 650.0


@patch("flight_search.get_flights")
def test_search_round_trip_returns_none_when_no_parseable_prices(mock_get_flights):
    mock_get_flights.return_value = Mock(flights=[Mock(price="indisponível")])

    assert search_round_trip("GRU", "LIS", "2026-11-10", "2026-11-24") is None


def test_iterate_flexible_dates_steps_through_window():
    pairs = list(iterate_flexible_dates("2026-11-01", "2026-11-15", trip_length_days=14, granularity_days=7))

    assert pairs == [
        ("2026-11-01", "2026-11-15"),
        ("2026-11-08", "2026-11-22"),
        ("2026-11-15", "2026-11-29"),
    ]


def test_find_cheapest_for_destination_fixed_mode_single_search():
    calls = []

    def fake_search(origin, to_airport, depart_date, return_date):
        calls.append((origin, to_airport, depart_date, return_date))
        return 3000.0

    dates_config = {"mode": "fixed", "depart_date": "2026-11-10", "return_date": "2026-11-24"}

    result = find_cheapest_for_destination(["GRU"], "LIS", dates_config, search_fn=fake_search)

    assert result == {"price": 3000.0, "depart_date": "2026-11-10", "return_date": "2026-11-24"}
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

    assert result == {"price": 2900.0, "depart_date": "2026-11-08", "return_date": "2026-11-22"}


def test_find_cheapest_for_destination_tries_every_origin_airport():
    prices_by_origin = {"GRU": 3200.0, "CGH": 2950.0}

    def fake_search(origin, to_airport, depart_date, return_date):
        return prices_by_origin[origin]

    dates_config = {"mode": "fixed", "depart_date": "2026-11-10", "return_date": "2026-11-24"}

    result = find_cheapest_for_destination(["GRU", "CGH"], "LIS", dates_config, search_fn=fake_search)

    assert result["price"] == 2950.0


def test_find_cheapest_for_destination_returns_none_when_every_search_fails():
    result = find_cheapest_for_destination(
        ["GRU"],
        "LIS",
        {"mode": "fixed", "depart_date": "2026-11-10", "return_date": "2026-11-24"},
        search_fn=lambda *a: None,
    )

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_flight_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'flight_search'`

- [ ] **Step 3: Write the implementation**

```python
# flight_search.py
from datetime import date, timedelta
from typing import Iterator, Optional

from fast_flights import FlightData, Passengers, get_flights


def _parse_price(price_str: str) -> Optional[float]:
    """Convert a price string like '$1,234.56' or 'R$ 1.234,56' into a float."""
    digits = "".join(ch for ch in price_str if ch.isdigit() or ch in ".,")
    if not digits:
        return None

    if "," in digits and "." in digits:
        digits = digits.replace(".", "").replace(",", ".")
    elif "," in digits:
        digits = digits.replace(",", "")

    try:
        return float(digits)
    except ValueError:
        return None


def search_round_trip(from_airport: str, to_airport: str, depart_date: str, return_date: str) -> Optional[float]:
    """Query Google Flights for a round trip and return the cheapest price found, or None."""
    result = get_flights(
        flight_data=[
            FlightData(date=depart_date, from_airport=from_airport, to_airport=to_airport),
            FlightData(date=return_date, from_airport=to_airport, to_airport=from_airport),
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=1, children=0, infants_in_seat=0, infants_on_lap=0),
        fetch_mode="fallback",
    )

    prices = [p for p in (_parse_price(flight.price) for flight in result.flights) if p is not None]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_flight_search.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add flight_search.py tests/test_flight_search.py
git commit -m "Add flight_search wrapper around fast-flights"
```

- [ ] **Step 6: Manual integration smoke test (not part of the automated suite)**

Run locally once, after `pip install -r requirements-dev.txt`, to confirm the
real `fast-flights` API matches what Task 4 assumed:

```bash
python -c "from flight_search import search_round_trip; print(search_round_trip('GRU', 'LIS', '2026-11-10', '2026-11-24'))"
```

Expected: prints a float price (or `None` if that exact date has no fares —
try a nearer date if so). **Check what currency the underlying prices are
in** (inspect `flight.price` strings) — if they come back in USD rather than
BRL, note it in `config.yaml`'s comments and treat `price_ceiling_brl` /
`drop_pct_threshold` as applying to whatever currency `fast-flights`
actually returns. If the import itself fails, check the installed
`fast-flights` version's README for the current `get_flights`/`FlightData`/
`Passengers` signature and adjust `flight_search.py` accordingly before
continuing — this step must pass before Task 6 is exercised end-to-end.

---

### Task 5: Notification channels

**Files:**
- Create: `notifiers/__init__.py`
- Create: `notifiers/telegram.py`
- Create: `notifiers/discord.py`
- Create: `notifiers/email.py`
- Test: `tests/test_notifiers.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `send_telegram(token: str, chat_id: str, message: str) -> bool`, `send_discord(webhook_url: str, message: str) -> bool`, `send_email(smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str, to_addr: str, subject: str, message: str) -> bool` — all used by Task 6 (`main.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_notifiers.py
from unittest.mock import Mock, patch

from notifiers.discord import send_discord
from notifiers.email import send_email
from notifiers.telegram import send_telegram


@patch("notifiers.telegram.requests.post")
def test_send_telegram_posts_to_bot_api_and_returns_true_on_success(mock_post):
    mock_post.return_value = Mock(ok=True)

    result = send_telegram("TOKEN", "CHAT_ID", "preço bom")

    assert result is True
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert kwargs["json"] == {"chat_id": "CHAT_ID", "text": "preço bom"}


@patch("notifiers.telegram.requests.post")
def test_send_telegram_returns_false_on_failure(mock_post):
    mock_post.return_value = Mock(ok=False)
    assert send_telegram("TOKEN", "CHAT_ID", "msg") is False


@patch("notifiers.discord.requests.post")
def test_send_discord_posts_to_webhook_url(mock_post):
    mock_post.return_value = Mock(ok=True)

    result = send_discord("https://discord.com/api/webhooks/x/y", "preço bom")

    assert result is True
    args, kwargs = mock_post.call_args
    assert args[0] == "https://discord.com/api/webhooks/x/y"
    assert kwargs["json"] == {"content": "preço bom"}


@patch("notifiers.email.smtplib.SMTP")
def test_send_email_logs_in_and_sends_returns_true_on_success(mock_smtp_class):
    mock_server = Mock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    result = send_email(
        "smtp.gmail.com", 587, "me@gmail.com", "app-password", "to@example.com", "Alerta", "preço bom"
    )

    assert result is True
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("me@gmail.com", "app-password")
    mock_server.sendmail.assert_called_once()


@patch("notifiers.email.smtplib.SMTP")
def test_send_email_returns_false_when_smtp_raises(mock_smtp_class):
    mock_smtp_class.return_value.__enter__.side_effect = RuntimeError("smtp down")

    result = send_email(
        "smtp.gmail.com", 587, "me@gmail.com", "app-password", "to@example.com", "Alerta", "preço bom"
    )

    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_notifiers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'notifiers'`

- [ ] **Step 3: Write the implementation**

```python
# notifiers/__init__.py
```

```python
# notifiers/telegram.py
import requests


def send_telegram(token: str, chat_id: str, message: str) -> bool:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=10,
    )
    return response.ok
```

```python
# notifiers/discord.py
import requests


def send_discord(webhook_url: str, message: str) -> bool:
    response = requests.post(webhook_url, json={"content": message}, timeout=10)
    return response.ok
```

```python
# notifiers/email.py
import smtplib
from email.mime.text import MIMEText


def send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    to_addr: str,
    subject: str,
    message: str,
) -> bool:
    msg = MIMEText(message, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [to_addr], msg.as_string())
        return True
    except Exception:  # noqa: BLE001 - any SMTP failure must not crash the run
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notifiers.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add notifiers/ tests/test_notifiers.py
git commit -m "Add Telegram, Discord and e-mail notifiers"
```

---

### Task 6: Orchestration (`main.py`)

**Files:**
- Create: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `should_alert` (Task 2), `load_history`/`save_history`/`make_key`/`update_entry` (Task 3), `find_cheapest_for_destination`/`search_round_trip` (Task 4), `send_telegram`/`send_discord`/`send_email` (Task 5).
- Produces: `process_destinations(destinations, origin_airports, dates_config, alerts_config, history, search_fn, notify_fns, now_fn=...) -> dict` (new history) and `main()` entrypoint — nothing downstream depends on these beyond the workflow invoking `python main.py`.

- [ ] **Step 1: Write the failing tests**

```python
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
    assert new_history["LIS|2026-11-10|2026-11-24"]["lowest_price_brl"] == 3000.0


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Write the implementation**

```python
# main.py
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from alert_engine import should_alert
from flight_search import find_cheapest_for_destination, search_round_trip
from notifiers.discord import send_discord
from notifiers.email import send_email
from notifiers.telegram import send_telegram
from price_store import load_history, make_key, save_history, update_entry

CONFIG_FILE = Path("config.yaml")
HISTORY_FILE = Path("data/price_history.json")


def format_message(name, airport, price, depart_date, return_date, ceiling):
    ceiling_note = f" (teto: {ceiling:.2f})" if ceiling is not None else ""
    return (
        f"✈️ {name} ({airport}) por {price:.2f} "
        f"(ida {depart_date}, volta {return_date}){ceiling_note}"
    )


def process_destinations(
    destinations,
    origin_airports,
    dates_config,
    alerts_config,
    history,
    search_fn,
    notify_fns,
    now_fn=lambda: datetime.now(timezone.utc).isoformat(),
):
    new_history = dict(history)

    for dest in destinations:
        name = dest["country"]
        airport = dest["airport"]
        ceiling = dest.get("price_ceiling_brl", alerts_config.get("price_ceiling_brl"))
        drop_pct = alerts_config.get("drop_pct_threshold")

        try:
            best = find_cheapest_for_destination(origin_airports, airport, dates_config, search_fn)
        except Exception as exc:  # noqa: BLE001 - one bad destination must not stop the batch
            print(f"[WARN] Falha ao buscar '{name}' ({airport}): {exc}", file=sys.stderr)
            continue

        if best is None:
            print(f"[WARN] Nenhum preço encontrado para '{name}' ({airport})", file=sys.stderr)
            continue

        price = best["price"]
        depart_date = best["depart_date"]
        return_date = best["return_date"]
        key = make_key(airport, depart_date, return_date)
        lowest_price_seen = history.get(key, {}).get("lowest_price_brl")

        if should_alert(price, ceiling, lowest_price_seen, drop_pct):
            message = format_message(name, airport, price, depart_date, return_date, ceiling)
            for notify in notify_fns:
                try:
                    result = notify(message)
                    if result is False:
                        print(f"[WARN] Canal rejeitou a notificação de '{name}'", file=sys.stderr)
                except Exception as exc:  # noqa: BLE001 - one bad channel must not stop the batch
                    print(f"[WARN] Falha ao notificar '{name}' via {notify!r}: {exc}", file=sys.stderr)
                    continue

        new_history = update_entry(new_history, key, name, price, now_fn())

    return new_history


def main() -> None:
    config = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    history = load_history(HISTORY_FILE)

    notify_fns = []

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if config["notifications"].get("telegram") and telegram_token and telegram_chat_id:
        notify_fns.append(lambda msg: send_telegram(telegram_token, telegram_chat_id, msg))
    else:
        print("[INFO] Telegram não configurado - pulando esse canal.", file=sys.stderr)

    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if config["notifications"].get("discord") and discord_webhook:
        notify_fns.append(lambda msg: send_discord(discord_webhook, msg))
    else:
        print("[INFO] Discord não configurado - pulando esse canal.", file=sys.stderr)

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    email_to = os.environ.get("EMAIL_TO")
    if config["notifications"].get("email") and all([smtp_host, smtp_port, smtp_user, smtp_password, email_to]):
        notify_fns.append(
            lambda msg: send_email(
                smtp_host, int(smtp_port), smtp_user, smtp_password, email_to, "Alerta de preço de passagem", msg
            )
        )
    else:
        print("[INFO] E-mail não configurado - pulando esse canal.", file=sys.stderr)

    new_history = process_destinations(
        destinations=config["destinations"],
        origin_airports=config["origin"],
        dates_config=config["dates"],
        alerts_config=config["alerts"],
        history=history,
        search_fn=search_round_trip,
        notify_fns=notify_fns,
    )

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_history(HISTORY_FILE, new_history)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: 7 passed

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: 33 passed (6 alert_engine + 6 price_store + 9 flight_search + 5 notifiers + 7 main), 0 failed

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "Add main.py orchestration entrypoint"
```

---

### Task 7: GitHub Actions workflow and deployment

**Files:**
- Create: `.github/workflows/check-flights.yml`

**Interfaces:**
- Consumes: `main.py` (Task 6) as the invoked script; `config.yaml` (Task 1) for behavior; GitHub Actions repository secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_WEBHOOK_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO`).
- Produces: nothing further downstream — this is the deployment surface.

- [ ] **Step 1: Create the workflow file**

```yaml
# .github/workflows/check-flights.yml
name: Check flight prices

on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch: {}

permissions:
  contents: write

concurrency:
  group: check-flights
  cancel-in-progress: false

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run flight price check
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
        run: python main.py

      - name: Commit updated price history
        run: |
          git config user.name "flight-price-monitor-bot"
          git config user.email "actions@users.noreply.github.com"
          git add data/price_history.json
          git diff --cached --quiet || git commit -m "Update price history [skip ci]"
          git push
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/check-flights.yml
git commit -m "Add GitHub Actions workflow for scheduled flight price checks"
```

- [ ] **Step 3: Push the repo to GitHub and complete one-time setup**

This step is manual (outside the code the agent writes) and must be done by
the user before the schedule can run for real:

1. Create a **public** GitHub repository named `flight-price-monitor` and
   push this local repo to it (public repos get unlimited free Actions
   minutes; the price history is not sensitive data).
2. Follow the "Configuração (uma vez só)" section of `README.md` to create
   the Telegram bot, Discord webhook, and SMTP app password, and add all
   eight secrets under **Settings → Secrets and variables → Actions**.
3. Edit `config.yaml` with the real candidate destinations and date window
   desired.

- [ ] **Step 4: Manual verification run (per spec's testing plan)**

1. In the GitHub repo's **Actions** tab, run **Check flight prices** via
   **Run workflow** (`workflow_dispatch`) with `config.yaml` limited to 1-2
   destinations and a deliberately high `price_ceiling_brl` (e.g. `999999`)
   so an alert is guaranteed to fire.
2. Confirm a message arrives on Telegram, Discord, and e-mail.
3. Confirm `data/price_history.json` was created/updated and committed by
   the workflow run (check the repo's commit history).
4. Set `price_ceiling_brl` back to a realistic value in `config.yaml` and
   commit.
5. Only after this manual run looks correct end-to-end, leave the `*/30 * * * *`
   cron schedule enabled (it already is, from Step 1) so it runs
   automatically going forward.

---

## Self-Review Notes

- **Spec coverage:** config data model (Task 1), alert logic with ceiling OR
  drop-% (Task 2), price history with monotonically-decreasing lowest
  (Task 3), Google Flights search incl. flexible-date and multi-origin
  scanning (Task 4), all three notification channels (Task 5), orchestration
  wiring config → search → history → alert → notify (Task 6), and the
  GitHub Actions cron + one-time setup + manual verification (Task 7) are
  each covered by one task.
- **Currency caveat:** flagged explicitly in Task 4 Step 6 and in the
  README, since `fast-flights` may return USD rather than BRL depending on
  the query — this is a real unknown until the manual smoke test runs, so
  it is surfaced rather than assumed away.
- **Type consistency checked:** `find_cheapest_for_destination` returns
  `{"price", "depart_date", "return_date"}` in Task 4, and Task 6's
  `process_destinations` destructures exactly those three keys from `best`.
  `make_key(airport, depart_date, return_date)` signature matches every call
  site in Task 6. `should_alert`'s four positional/keyword parameters match
  between Task 2's definition and Task 6's call.
