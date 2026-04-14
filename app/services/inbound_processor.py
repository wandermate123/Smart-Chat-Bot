import asyncio
import logging
from typing import Any

from app.config import Settings
from app.db import repo as db_repo
from app.db.idempotency import IdempotencyStore
from app.db.stage_store import StageStore
from app.services.whatsapp_send import send_text_message

logger = logging.getLogger(__name__)

_QUALIFIER_REPLY = (
    "Got it \U0001f44d Main aapke liye Varanasi circuit mein ek plan set karta hoon. "
    "Pehle bata do: kitne din ka trip soch rahe ho — 2N/3N ya 3N/4N? \U0001f60a"
)

_QUALIFICATION_REPLY = (
    "Theek hai \U0001f60a Approx budget bata do (per person ya total), aur kitne log hain? "
    "Phir main options suggest karunga."
)


def _extract_inbound_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                out.append({"value": value, "message": msg})
    return out


def _reply_for_stage(stage_before: str, msg_type: str | None, text: str) -> str | None:
    if msg_type == "text" and not (text or "").strip():
        return (
            "WanderMate here \U0001f44b Aap apna message dubara bhej sakte ho?"
        )
    if msg_type != "text":
        return (
            "Abhi main text messages best handle karta hoon. "
            "Jo bhi plan chahiye, type karke bhej do."
        )
    if stage_before == "greeting":
        return _QUALIFIER_REPLY
    if stage_before == "qualification":
        return _QUALIFICATION_REPLY
    return (
        "Samajh gaya. Team jald details share karegi — ya aap dates / city dubara bhej dena."
    )


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

        conv_id: int | None = None
        stage_before = "greeting"

        if settings.database_url:
            try:
                conv_id, stage_before = await asyncio.to_thread(
                    db_repo.record_inbound,
                    settings.database_url,
                    wa_id,
                    wam_id,
                    msg_type,
                    text,
                    msg,
                )
            except Exception:
                logger.exception("DB record_inbound failed; continuing without persist")
                stage_before = "greeting"
        else:

            def _local_stage() -> str:
                st = StageStore(settings.idempotency_db_path)
                s = st.get(wa_id)
                if s == "greeting" and msg_type == "text" and (text or "").strip():
                    st.set(wa_id, "qualification")
                return s

            stage_before = await asyncio.to_thread(_local_stage)

        reply = _reply_for_stage(stage_before, msg_type, text)
        if not reply:
            continue

        send_result = await send_text_message(settings, wa_id, reply)
        out_wam_id = None
        if isinstance(send_result, dict):
            m = send_result.get("messages") or []
            if m and isinstance(m[0], dict):
                out_wam_id = m[0].get("id")

        if settings.database_url and conv_id is not None:
            try:
                await asyncio.to_thread(
                    db_repo.record_outbound,
                    settings.database_url,
                    conv_id,
                    reply,
                    out_wam_id,
                )
            except Exception:
                logger.exception("DB record_outbound failed")
