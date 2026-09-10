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
