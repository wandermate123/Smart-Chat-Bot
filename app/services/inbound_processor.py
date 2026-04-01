import logging
from typing import Any

from app.config import Settings
from app.db.idempotency import IdempotencyStore
from app.services.whatsapp_send import send_text_message

logger = logging.getLogger(__name__)


def _extract_inbound_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                out.append({"value": value, "message": msg})
    return out


async def process_whatsapp_payload(
    payload: dict[str, Any],
    settings: Settings,
    idempotency: IdempotencyStore,
) -> None:
    for item in _extract_inbound_messages(payload):
        msg = item["message"]
        wam_id = msg.get("id")
        if not wam_id:
            continue
        if idempotency.seen(wam_id):
            logger.debug("Duplicate wam_id %s skipped", wam_id)
            continue
        idempotency.mark(wam_id)

        wa_id = msg.get("from")
        msg_type = msg.get("type")
        text = (msg.get("text") or {}).get("body", "")

        logger.info(
            "Inbound message wam_id=%s from=%s type=%s text=%r",
            wam_id,
            wa_id,
            msg_type,
            text[:200] if text else "",
        )

        if not wa_id:
            continue

        if msg_type == "text" and text.strip():
            reply = (
                "Got it 👍 Main aapke liye Varanasi circuit mein ek plan set karta hoon. "
                "Pehle bata do: kitne din ka trip soch rahe ho — 2N/3N ya 3N/4N? 😊"
            )
            await send_text_message(settings, wa_id, reply)
        elif msg_type == "text":
            await send_text_message(
                settings,
                wa_id,
                "WanderMate here 👋 Aap apna message dubara bhej sakte ho?",
            )
