import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

# WhatsApp Cloud API: max 3 reply buttons; title max 20 characters.
_MAX_BUTTONS = 3
_MAX_BUTTON_TITLE_LEN = 20


def _graph_messages_url(settings: Settings) -> str:
    return (
        f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )


async def send_text_message(
    settings: Settings,
    to_wa_id: str,
    body: str,
) -> dict | None:

    if not settings.outbound_reply_enabled:
        logger.info("Outbound disabled; skip send to %s", to_wa_id)
        return None

    url = _graph_messages_url(settings)
    headers = {
        "Authorization": f"Bearer {settings.meta_whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            logger.error(
                "WhatsApp send failed: %s %s", r.status_code, r.text[:500]
            )
            return None
        return r.json()


async def send_interactive_buttons(
    settings: Settings,
    to_wa_id: str,
    body: str,
    buttons: list[tuple[str, str]],
    *,
    footer: str | None = None,
) -> dict[str, Any] | None:
    """Send type=interactive button message (1–3 reply buttons)."""
    if not settings.outbound_reply_enabled:
        logger.info("Outbound disabled; skip interactive send to %s", to_wa_id)
        return None

    if not buttons:
        logger.error("interactive buttons: empty list")
        return None
    if len(buttons) > _MAX_BUTTONS:
        logger.error("interactive buttons: max %s, got %s", _MAX_BUTTONS, len(buttons))
        return None

    action_buttons: list[dict[str, Any]] = []
    for bid, title in buttons:
        t = (title or "").strip()
        if len(t) > _MAX_BUTTON_TITLE_LEN:
            logger.error("Button title too long (%s): %r", len(t), t)
            return None
        action_buttons.append(
            {"type": "reply", "reply": {"id": str(bid), "title": t}}
        )

    interactive: dict[str, Any] = {
        "type": "button",
        "body": {"text": body},
        "action": {"buttons": action_buttons},
    }
    if footer:
        interactive["footer"] = {"text": footer[:60]}

    url = _graph_messages_url(settings)
    headers = {
        "Authorization": f"Bearer {settings.meta_whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": interactive,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            logger.error(
                "WhatsApp interactive send failed: %s %s",
                r.status_code,
                r.text[:500],
            )
            return None
        return r.json()
