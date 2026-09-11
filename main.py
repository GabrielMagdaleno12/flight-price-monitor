# main.py
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from alert_engine import should_alert
from flight_search import find_cheapest_for_destination, search_round_trip
from notifiers.discord import send_discord
from notifiers.email import send_email
from notifiers.telegram import send_telegram
from price_store import load_history, make_key, save_history, update_entry

CONFIG_FILE = Path("config.yaml")
HISTORY_FILE = Path("data/price_history.json")


def format_message(name, origin, airport, price, depart_date, return_date, ceiling):
    # Only mention the ceiling when it's actually why we're at/under it -- a
    # drop-% alert can fire on a price above the ceiling, and printing
    # "(teto: X)" next to a price higher than X reads as a bug.
    ceiling_note = f" (teto: R$ {ceiling:.2f})" if ceiling is not None and price <= ceiling else ""
    return (
        f"✈️ {name} ({origin} → {airport}) por R$ {price:.2f} "
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
    now_fn=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    stats: Optional[dict] = None,
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
            if stats is not None:
                stats["attempted"] = stats.get("attempted", 0) + 1
            continue

        if best is None:
            print(f"[WARN] Nenhum preço encontrado para '{name}' ({airport})", file=sys.stderr)
            if stats is not None:
                stats["attempted"] = stats.get("attempted", 0) + 1
            continue

        if stats is not None:
            stats["attempted"] = stats.get("attempted", 0) + 1
            stats["found"] = stats.get("found", 0) + 1

        price = best["price"]
        origin = best["origin"]
        depart_date = best["depart_date"]
        return_date = best["return_date"]
        key = make_key(airport, depart_date, return_date)
        existing_entry = history.get(key, {})
        lowest_price_seen = existing_entry.get("lowest_price_brl")
        last_alerted_price = existing_entry.get("last_alerted_price")

        alerted_price = None
        if should_alert(price, ceiling, lowest_price_seen, drop_pct):
            # Re-alert only if this qualifying price is an improvement over the
            # last one we actually notified for -- otherwise the same
            # qualifying price would re-alert every run forever.
            if last_alerted_price is None or price < last_alerted_price:
                message = format_message(name, origin, airport, price, depart_date, return_date, ceiling)
                any_channel_sent = False
                for notify in notify_fns:
                    try:
                        result = notify(message)
                        if result is False:
                            print(f"[WARN] Canal rejeitou a notificação de '{name}'", file=sys.stderr)
                        else:
                            any_channel_sent = True
                    except Exception as exc:  # noqa: BLE001 - one bad channel must not stop the batch
                        # Don't log the exception text itself: for Telegram it can
                        # embed the bot token in the request URL, and for Discord
                        # the webhook URL itself is the secret.
                        print(
                            f"[WARN] Falha ao notificar '{name}': {type(exc).__name__}",
                            file=sys.stderr,
                        )
                        continue
                # Only mark this price as "alerted" if some channel actually
                # delivered it -- otherwise an outage (or zero channels
                # configured) would permanently suppress a real alert the
                # user never received, since the same or a worse price would
                # never re-trigger afterward.
                if any_channel_sent:
                    alerted_price = price
                else:
                    print(
                        f"[WARN] Nenhum canal notificou '{name}' com sucesso; não marcando como alertado.",
                        file=sys.stderr,
                    )

        new_history = update_entry(new_history, key, name, price, now_fn(), alerted_price=alerted_price)

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

    destinations = config.get("destinations") or []
    origin_airports = config.get("origin") or []

    stats = {"attempted": 0, "found": 0}
    new_history = process_destinations(
        destinations=destinations,
        origin_airports=origin_airports,
        dates_config=config["dates"],
        alerts_config=config["alerts"],
        history=history,
        search_fn=search_round_trip,
        notify_fns=notify_fns,
        stats=stats,
    )

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_history(HISTORY_FILE, new_history)

    if destinations and stats["found"] == 0:
        # Every destination search failed this run (e.g. Google blocked the
        # runner's IP) -- exit non-zero so the GitHub Actions run shows red.
        # This is a process exit code, not a notification, so it doesn't
        # violate the "no per-failure alerting" non-goal.
        print(
            f"[ERROR] Nenhum preço encontrado em nenhum dos {len(destinations)} destino(s); "
            "abortando com falha.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
