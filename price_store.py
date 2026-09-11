# price_store.py
import json
import sys
from pathlib import Path


def load_history(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # A corrupted history file must not wedge every future run: log it and
        # start from an empty history so the next save rewrites a valid file.
        print(f"[WARN] Histórico corrompido em {path} ({exc}); recomeçando vazio.", file=sys.stderr)
        return {}


def save_history(path: Path, history: dict) -> None:
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


def make_key(airport: str, depart_date: str, return_date: str) -> str:
    return f"{airport}|{depart_date}|{return_date}"


def update_entry(
    history: dict,
    key: str,
    destination_name: str,
    price: float,
    checked_at: str,
    alerted_price: float = None,
) -> dict:
    """Return a new history dict with `key` updated for this run.

    `alerted_price` is the price a notification was actually sent for on this
    run (or None when no notification was sent). It is stored as
    `last_alerted_price` and is what de-duplicates repeat alerts for the same
    qualifying price across runs; when None, any previously recorded value is
    preserved.
    """
    new_history = dict(history)
    existing = new_history.get(key)

    if existing is None:
        new_history[key] = {
            "destination": destination_name,
            "lowest_price_brl": price,
            "last_price_brl": price,
            "last_alerted_price": alerted_price,
            "first_seen": checked_at,
            "last_checked": checked_at,
        }
    else:
        updated = dict(existing)
        updated["lowest_price_brl"] = min(existing["lowest_price_brl"], price)
        updated["last_price_brl"] = price
        updated["last_checked"] = checked_at
        if alerted_price is not None:
            updated["last_alerted_price"] = alerted_price
        else:
            updated.setdefault("last_alerted_price", None)
        new_history[key] = updated

    return new_history
