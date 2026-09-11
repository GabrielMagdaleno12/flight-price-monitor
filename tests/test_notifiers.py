from unittest.mock import Mock, patch

import pytest

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
def test_send_email_propagates_exception_when_smtp_raises(mock_smtp_class):
    # Consistent error contract across all three notifiers: let the
    # underlying exception propagate (like telegram/discord's requests
    # exceptions) rather than swallowing it and returning False. main.py's
    # per-channel try/except is what actually catches this.
    mock_smtp_class.return_value.__enter__.side_effect = RuntimeError("smtp down")

    with pytest.raises(RuntimeError):
        send_email("smtp.gmail.com", 587, "me@gmail.com", "app-password", "to@example.com", "Alerta", "preço bom")
