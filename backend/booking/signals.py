from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Booking

import os
import requests


def _get_bot_token() -> str:
    """Read BOT_TOKEN from environment."""
    return os.getenv("BOT_TOKEN", "").strip()


@receiver(post_save, sender=Booking)
def notify_admin(sender, instance, created, **kwargs):
    if not created:
        return

    bot_token = _get_bot_token()
    if not bot_token:
        # Token not configured -> skip Telegram notifications
        return

    # Partner tekshiruvi
    if not instance.obj or not instance.obj.partner:
        return

    telegram_id = instance.obj.partner.telegram_id
    if not telegram_id:
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": int(telegram_id),
        "text": (
            "🆕 Yangi bron!\n\n"
            f"👤 Ism: {instance.client_name}\n"
            f"📅 Sana: {instance.date_from} — {instance.date_to}"
        ),
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Telegram xato:", e)
