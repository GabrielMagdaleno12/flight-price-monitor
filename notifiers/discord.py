import requests


def send_discord(webhook_url: str, message: str) -> bool:
    response = requests.post(webhook_url, json={"content": message}, timeout=10)
    return response.ok
