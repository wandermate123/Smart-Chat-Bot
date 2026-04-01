import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


async def send_text_message(
    settings: Settings,
    to_wa_id: str,
    body: str,
) -> dict | None:

    if not settings.outbound_reply_enabled:
        logger.info("Outbound disabled; skip send to %s", to_wa_id)
        return None

    url = (
        f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )
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
