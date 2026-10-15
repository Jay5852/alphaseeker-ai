"""Telegram Notification Dispatcher."""

import logging
import requests
from config.settings import telegram_config
from alerts.formatter import format_trade_ticket_text
from risk.manager import TradeOrderTicket

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token or telegram_config.bot_token
        self.chat_id = chat_id or telegram_config.chat_id
        self.enabled = bool(self.bot_token and self.chat_id)

    def send_message(self, text: str) -> bool:
        """Sends a markdown message to the configured Telegram chat."""
        if not self.enabled:
            logger.info("[Telegram Not Configured] Message simulated in logs:\n%s", text)
            print("\n" + "="*40 + "\n[TELEGRAM PREVIEW]\n" + text + "\n" + "="*40 + "\n")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Successfully dispatched Telegram alert.")
                return True
            else:
                logger.error("Failed to send Telegram message: %s", response.text)
                return False
        except Exception as e:
            logger.error("Telegram dispatch error: %s", str(e))
            return False

    def send_trade_ticket(self, ticket: TradeOrderTicket, pattern_name: str, notes: str = "", time_prediction=None, meta_label=None, confluence=None) -> bool:
        """Formats and sends a TradeOrderTicket alert with time prediction, meta-labeling, and confluence score."""
        message = format_trade_ticket_text(ticket, pattern_name, notes, time_prediction=time_prediction, meta_label=meta_label, confluence=confluence)
        return self.send_message(message)


telegram_notifier = TelegramNotifier()
