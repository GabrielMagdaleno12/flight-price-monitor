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
