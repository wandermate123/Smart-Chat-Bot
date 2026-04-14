import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal

from app.config import Settings
from app.db import repo as db_repo
from app.db.idempotency import IdempotencyStore
from app.db.stage_store import StageStore
from app.services.funnel_logic import (
    BUDGET_ASK_BODY,
    BUDGET_REPLY_BUTTONS,
    PROPOSAL_REPLY,
    TRIP_LENGTH_BODY,
    TRIP_REPLY_BUTTONS,
    followup_reply,
    qualification_satisfied,
)
from app.services.whatsapp_send import send_interactive_buttons, send_text_message

logger = logging.getLogger(__name__)


def _parse_inbound_message(
    msg: dict[str, Any],
) -> tuple[str | None, str, str | None]:
    """Return (msg_type, user_text, button_id). user_text is body or button title."""
    mt = msg.get("type")
    if mt == "text":
        body = (msg.get("text") or {}).get("body", "") or ""
        return mt, body, None
    if mt == "interactive":
        inter = msg.get("interactive") or {}
        if inter.get("type") == "button_reply":
            br = inter.get("button_reply") or {}
            bid = br.get("id")
            title = (br.get("title") or "").strip()
            return mt, title, str(bid) if bid is not None else None
    return mt, "", None


def _has_inbound_substance(
    msg_type: str | None, user_text: str, button_id: str | None
) -> bool:
    if msg_type == "text" and (user_text or "").strip():
        return True
    if msg_type == "interactive" and (button_id or "").strip():
        return True
    return False


@dataclass(frozen=True)
class OutboundPayload:
    kind: Literal["text", "interactive_buttons"]
    body: str
    buttons: list[tuple[str, str]] | None = None


def _outbound_log_body(payload: OutboundPayload) -> str:
    if payload.kind == "text":
        return payload.body
    parts = " | ".join(t for _, t in (payload.buttons or []))
    return f"{payload.body}\n[buttons: {parts}]"


def _outbound_for_stage(
    stage_before: str,
    msg_type: str | None,
    user_text: str,
    button_id: str | None,
    main_whatsapp_e164: str,
) -> OutboundPayload | None:
    if msg_type == "text" and not (user_text or "").strip():
        return OutboundPayload(
            "text",
            "WanderMate here \U0001f44b Aap apna message dubara bhej sakte ho?",
        )
    if msg_type == "interactive" and not (button_id or "").strip():
        return OutboundPayload(
            "text",
            "Option clear nahi hua — button dubara chuno ya type karke bhej do.",
        )
    if msg_type not in ("text", "interactive"):
        return OutboundPayload(
            "text",
            "Abhi main text messages aur quick buttons best handle karta hoon. "
            "Jo bhi plan chahiye, type karke bhej do.",
        )

    if stage_before == "greeting":
        return OutboundPayload(
            "interactive_buttons",
            TRIP_LENGTH_BODY,
            TRIP_REPLY_BUTTONS,
        )
    if stage_before == "qualification":
        if qualification_satisfied(user_text, button_id):
            return OutboundPayload("text", PROPOSAL_REPLY, None)
        return OutboundPayload(
            "interactive_buttons",
            BUDGET_ASK_BODY,
            BUDGET_REPLY_BUTTONS,
        )
    if stage_before == "proposal":
        return OutboundPayload("text", followup_reply(main_whatsapp_e164), None)
    return OutboundPayload(
        "text",
        "Samajh gaya. Team jald details share karegi — ya aap dates / city dubara bhej dena.",
    )


def _extract_inbound_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                out.append({"value": value, "message": msg})
    return out


def _interactive_fallback_text(payload: OutboundPayload) -> str:
    lines = [payload.body.strip(), ""]
    for _bid, title in payload.buttons or []:
        lines.append(f"• {title}")
    lines.append(
        "\n(Option chuno jo best lage — type bhi kar sakte ho, jaise: 2N/3N ya 20k 2 log.)"
    )
    body = "\n".join(lines).strip()
    return body[:4096]


async def process_whatsapp_payload(
    payload: dict[str, Any],
    settings: Settings,
    idempotency: IdempotencyStore,
) -> None:
    items = _extract_inbound_messages(payload)
    if not items:
        n_entry = len(payload.get("entry") or [])
        logger.info(
            "WhatsApp webhook: no user messages to process (often delivery status-only). "
            "object=%r entries=%s. Subscribe to messages + check user writes to this Cloud API number.",
            payload.get("object"),
            n_entry,
        )

    for item in items:
        msg = item["message"]
        wam_id = msg.get("id")
        if not wam_id:
            continue
        if idempotency.seen(wam_id):
            logger.info("Duplicate wam_id %s skipped (idempotency)", wam_id)
            continue

        wa_id = msg.get("from")
        msg_type, user_text, button_id = _parse_inbound_message(msg)

        logger.info(
            "Inbound message wam_id=%s from=%s type=%s text=%r button_id=%r",
            wam_id,
            wa_id,
            msg_type,
            (user_text or "")[:200],
            button_id,
        )

        if not wa_id:
            logger.warning("Inbound message missing from wa_id wam_id=%s", wam_id)
            continue

        conv_id: int | None = None
        stage_before = "greeting"
        has_substance = _has_inbound_substance(msg_type, user_text, button_id)

        if settings.database_url:
            try:
                conv_id, stage_before = await asyncio.to_thread(
                    db_repo.record_inbound,
                    settings.database_url,
                    wa_id,
                    wam_id,
                    msg_type,
                    user_text,
                    msg,
                    button_id,
                )
            except Exception:
                logger.exception("DB record_inbound failed; continuing without persist")
                stage_before = "greeting"
        else:

            def _local_stage() -> str:
                st = StageStore(settings.idempotency_db_path)
                s = st.get(wa_id)
                if s == "greeting" and has_substance:
                    st.set(wa_id, "qualification")
                    return s
                if (
                    s == "qualification"
                    and has_substance
                    and qualification_satisfied(user_text, button_id)
                ):
                    st.set(wa_id, "proposal")
                return s

            stage_before = await asyncio.to_thread(_local_stage)

        outbound = _outbound_for_stage(
            stage_before,
            msg_type,
            user_text,
            button_id,
            settings.main_whatsapp_e164,
        )
        if not outbound:
            continue

        if outbound.kind == "text":
            send_result = await send_text_message(settings, wa_id, outbound.body)
        else:
            send_result = await send_interactive_buttons(
                settings,
                wa_id,
                outbound.body,
                outbound.buttons or [],
            )
            if send_result is None:
                logger.warning(
                    "Interactive message failed for wa_id=%s — sending plain text fallback "
                    "(see Graph API error above; WABA tier / number / payload).",
                    wa_id,
                )
                send_result = await send_text_message(
                    settings, wa_id, _interactive_fallback_text(outbound)
                )

        if send_result is None:
            logger.error(
                "Outbound send failed for wa_id=%s outbound=%s — check "
                "META_WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, OUTBOUND_REPLY_ENABLED",
                wa_id,
                outbound.kind,
            )
            continue

        idempotency.mark(wam_id)

        log_body = _outbound_log_body(outbound)
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
                    log_body,
                    out_wam_id,
                )
            except Exception:
                logger.exception("DB record_outbound failed")
