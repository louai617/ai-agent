"""Notification dispatch.

Channels: desktop (Qt signal consumed by the tray icon), email (SMTP),
Telegram (bot API), optional WhatsApp (generic webhook, e.g. a Business API
gateway). Failures in one channel never block the others or the publisher.
"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

import requests

from app.core.config import NotificationConfig, get_config, get_secret
from app.core.logging import get_logger

logger = get_logger(__name__)


class Notifier:
    """Fan-out notifier. ``desktop_callback`` is wired to the UI tray icon."""

    def __init__(self, config: NotificationConfig | None = None) -> None:
        self._config = config or get_config().notifications
        self.desktop_callback = None  # set by the UI: Callable[[str, str], None]

    # ------------------------------------------------------------------ public

    def notify(self, title: str, message: str, level: str = "info") -> None:
        """Send to all enabled channels; log-and-continue on channel errors."""
        logger.info("Notification [%s] %s: %s", level, title, message)
        if self._config.desktop_enabled and self.desktop_callback is not None:
            try:
                self.desktop_callback(title, message)
            except Exception as exc:  # noqa: BLE001
                logger.error("Desktop notification failed: %s", exc)
        if self._config.email_enabled:
            self._send_email(title, message)
        if self._config.telegram_enabled:
            self._send_telegram(f"*{title}*\n{message}")
        if self._config.whatsapp_enabled:
            self._send_whatsapp(f"{title}: {message}")

    # Convenience wrappers used by the engine
    def property_published(self, ref: str, platform: str, url: str) -> None:
        self.notify("Property Published", f"{ref} published on {platform}: {url}", "success")

    def publish_failed(self, ref: str, platform: str, error: str) -> None:
        self.notify("Publish Failed", f"{ref} on {platform}: {error}", "error")

    def captcha_detected(self, platform: str) -> None:
        self.notify(
            "CAPTCHA Detected",
            f"{platform} is showing a CAPTCHA. Automation paused - open the browser window, "
            "solve it, then resume from the dashboard.",
            "warning",
        )

    def login_expired(self, platform: str, email: str) -> None:
        self.notify("Login Expired", f"Login failed for {email} on {platform}. Check credentials.", "warning")

    # ---------------------------------------------------------------- channels

    def _send_email(self, subject: str, body: str) -> None:
        cfg = self._config
        password = get_secret("SMTP_PASSWORD")
        if not (cfg.email_smtp_host and cfg.email_from and cfg.email_to):
            logger.warning("Email notification enabled but not fully configured")
            return
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = f"[Elite Publisher] {subject}"
            msg["From"] = cfg.email_from
            msg["To"] = ", ".join(cfg.email_to)
            with smtplib.SMTP(cfg.email_smtp_host, cfg.email_smtp_port, timeout=20) as server:
                server.starttls()
                if password:
                    server.login(cfg.email_from, password)
                server.sendmail(cfg.email_from, cfg.email_to, msg.as_string())
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("Email notification failed: %s", exc)

    def _send_telegram(self, text: str) -> None:
        token = get_secret("TELEGRAM_BOT_TOKEN")
        chat_id = self._config.telegram_chat_id
        if not (token and chat_id):
            logger.warning("Telegram notification enabled but token/chat_id missing")
            return
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Telegram notification failed: %s", exc)

    def _send_whatsapp(self, text: str) -> None:
        """Generic webhook POST - works with WhatsApp Business API gateways."""
        cfg = self._config
        token = get_secret("WHATSAPP_API_TOKEN")
        if not (cfg.whatsapp_api_url and cfg.whatsapp_to):
            logger.warning("WhatsApp notification enabled but not fully configured")
            return
        try:
            response = requests.post(
                cfg.whatsapp_api_url,
                json={"to": cfg.whatsapp_to, "type": "text", "text": {"body": text}},
                headers={"Authorization": f"Bearer {token}"} if token else {},
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("WhatsApp notification failed: %s", exc)
