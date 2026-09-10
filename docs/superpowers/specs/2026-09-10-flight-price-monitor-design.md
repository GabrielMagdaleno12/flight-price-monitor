# Flight Price Monitor — Design

## Goal

Monitor airfare prices for international trips departing from São Paulo
(GRU/CGH) and alert the user (Telegram + Discord + e-mail) when a good price
is found — either a fixed price ceiling or a meaningful percentage drop vs.
the historical lowest price seen. Must run entirely in the cloud (GitHub
Actions) so the user's PC does not need to be on, must cost nothing, and
must check every ~30 minutes.

## Non-goals

- No true "anywhere" map-style search (Google Flights "Explore"). Scraping
  that view is far more fragile than a normal route search. Instead, "any
  country with a good price" is approximated by looping over a **candidate
  destination list** the user maintains in config.
- No scraping of specific airline/OTA sites (LATAM, Decolar, etc.) in this
  version — flagged as a possible phase 2 once the Google Flights path is
  proven stable.
- No web UI/dashboard — config is a plain YAML file edited directly on
  GitHub; price history is a JSON file in the repo, browsable but not meant
  to be hand-edited.
- No per-failure alerting — a search failure for one destination is logged
  in the Actions run, not sent as a notification. Only price events are
  notified.
- Not a separate module in the existing `price-watcher` repo — this is a
  standalone repo per user's explicit request, even though it shares the
  same architectural pattern (GitHub Actions + committed JSON state).

## Architecture

```
GitHub repo (public)
├── config.yaml                  <- user-edited: origin, destinations, dates, thresholds
├── data/
│   └── price_history.json       <- lowest/last price per destination+date-window (committed back by the workflow)
├── flight_search.py             <- queries Google Flights (via fast-flights) for a route
├── price_store.py               <- reads/writes price_history.json
├── alert_engine.py              <- decides whether a found price is alert-worthy
├── notifiers/
│   ├── telegram.py
│   ├── discord.py
│   └── email.py
├── main.py                      <- orchestrates the whole run
├── requirements.txt
└── .github/workflows/
    └── check-flights.yml        <- cron schedule (every 30 min) + manual trigger
```

- **Trigger**: `schedule` (cron `*/30 * * * *`) and `workflow_dispatch`
  (manual "Run workflow" button, used for testing and on-demand checks).
- **Runner**: standard GitHub-hosted `ubuntu-latest` runner. Public repo =
  unlimited free Actions minutes.
- **Secrets**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_WEBHOOK_URL`,
  `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` — stored
  as encrypted GitHub Actions repository secrets, never committed to the repo.
- **Concurrency**: the workflow sets a `concurrency` group so overlapping
  runs (e.g. a manual trigger firing mid-cron) can't race on the
  `price_history.json` commit.

## Data model

`config.yaml`:
```yaml
origin: [GRU, CGH]

destinations:
  - country: "Portugal"
    airport: "LIS"
  - country: "Itália"
    airport: "FCO"
  - country: "Japão"
    airport: "NRT"
  # ... user's candidate list, as many as desired

dates:
  mode: flexible          # "fixed" or "flexible"
  # mode: fixed
  # depart_date: "2026-11-10"
  # return_date: "2026-11-24"
  window_start: "2026-11-01"
  window_end: "2027-02-28"
  trip_length_days: 14
  granularity_days: 7     # step size when scanning the flexible window (keeps run time bounded)

alerts:
  price_ceiling_brl: 3500        # global default; a destination can override with its own "price_ceiling_brl"
  drop_pct_threshold: 15         # alert when price falls at least this % below the recorded lowest

notifications:
  telegram: true
  discord: true
  email: true
```

`data/price_history.json` (auto-managed):
```json
{
  "LIS|2026-11-10|2026-11-24": {
    "destination": "Portugal",
    "lowest_price_brl": 3180.50,
    "last_price_brl": 3180.50,
    "last_checked": "2026-09-10T14:00:00Z",
    "first_seen": "2026-09-10T08:00:00Z"
  }
}
```
Key = `airport|depart_date|return_date`, so fixed and flexible modes share
the same storage shape (flexible mode just produces more keys, one per
date combination scanned).

## Flight search

`flight_search.py` wraps the `fast-flights` library (unofficial Google
Flights client, no browser needed) to fetch the cheapest round-trip price
for a given origin/destination/date pair.

- **Fixed mode**: one search per destination, for the exact configured
  dates.
- **Flexible mode**: for each destination, iterate depart dates from
  `window_start` to `window_end` in steps of `granularity_days`, each paired
  with a return date `trip_length_days` later; keep the cheapest result.
  This keeps the number of queries bounded (e.g. a 4-month window with
  7-day steps ≈ 17 searches per destination, not hundreds), so a run
  finishes well within a 30-minute cycle even with several destinations.

A failed search for one destination/date combo (rate limit, no results,
network error) is caught, logged to the workflow output, and skipped — it
does not stop the rest of the batch.

## Alert logic

For each destination (using its cheapest price found this run):
- Alert if `current_price <= price_ceiling` (destination's own ceiling, or
  the global default).
- Alert if `current_price <= lowest_price_brl * (1 - drop_pct_threshold/100)`
  compared to the historical lowest recorded for that destination+date key.
- Either condition alone is enough to trigger a notification (per user's
  choice of "both combined" as *either*, not requiring both at once).
- After evaluating, `price_history.json` is updated: `lowest_price_brl` only
  decreases (keeps the all-time low), `last_price_brl`/`last_checked` always
  refresh.

## Notifications

All three channels receive the same message on an alert, e.g.:
`"✈️ Portugal (LIS) por R$ 3.180,50 (ida 10/11, volta 24/11) — abaixo do teto de R$ 3.500"`

- **Telegram**: `POST https://api.telegram.org/bot<token>/sendMessage`.
- **Discord**: `POST` to the channel webhook URL.
- **E-mail**: SMTP (`smtplib`), using the user's provider credentials (e.g.
  Gmail App Password) stored as secrets.

Each channel is attempted independently; a failure in one (bad token,
SMTP timeout) is logged and does not block the others.

## Error handling

- A failed search for one destination/date combo is caught, logged, and
  skipped — does not stop the batch.
- Missing notification secrets → that channel is skipped (logged), so
  partial setup (e.g. only Telegram configured) still works.
- `concurrency` group on the workflow prevents two runs from racing on the
  `price_history.json` commit.

## Testing plan

1. Unit tests for `alert_engine.should_alert` (ceiling only, drop % only,
   both, neither) — pure function, no network.
2. Unit tests for `price_store` read/write/update-lowest logic.
3. `flight_search` tested with the real `fast-flights` call mocked out, so
   CI tests don't depend on network/Google availability.
4. Manual run via `workflow_dispatch` with 1-2 destinations and a
   deliberately high `price_ceiling_brl` to confirm an alert fires on all
   three channels.
5. Confirm `price_history.json` is committed back correctly after a run.
6. Only after manual runs look correct, rely on the 30-minute cron.

## One-time setup (user does this, outside of code)

1. Create a Telegram bot via @BotFather → get bot token; message the bot
   once → note the chat ID.
2. Create a Discord webhook in a server/channel the user owns → get the
   webhook URL.
3. Generate an SMTP app password (e.g. Gmail App Password) for sending
   e-mail.
4. Create the GitHub repo (`flight-price-monitor`, public) and add the
   secrets under Settings → Secrets and variables → Actions.
5. Edit `config.yaml` with the desired candidate destinations and date
   window.

## Rejected alternatives

- **Extending the existing `price-watcher` repo**: would reuse proven
  notifier code, but the user explicitly asked for a separate repo/folder
  for this project.
- **Google Flights "Explore" (anywhere) scraping**: far more fragile
  (map-based UI, heavy JS, no stable unofficial client) than a normal route
  search; replaced with a user-maintained candidate destination list.
- **Playwright/browser scraping of Google Flights + specific airline/OTA
  sites in v1**: more coverage, but much higher fragility and CI runtime
  cost; deferred to a possible phase 2.
- **Paid flight API (Amadeus/Kiwi/Skyscanner)**: rejected per user's
  preference for Google Flights + specific sites over a paid API.
