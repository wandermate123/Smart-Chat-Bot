"""Synchronous DB access — call from asyncio.to_thread in FastAPI handlers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import get_engine
from app.db.models import Conversation, Message, User
from app.services.funnel_logic import qualification_satisfied

logger = logging.getLogger(__name__)


def _session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False)


def record_inbound(
    database_url: str,
    wa_id: str,
    wam_id: str,
    msg_type: str | None,
    text: str,
    raw_msg: dict[str, Any],
    button_id: str | None = None,
) -> tuple[int, str]:
    """Persist inbound message; advance greeting → qualification on first real input.

    ``text`` is message body or button title. ``button_id`` set for interactive replies.

    Returns (conversation_id, stage_before) for reply routing.
    """
    sf = _session_factory(database_url)
    conv_id: int
    stage_before: str
    with sf() as session:
        with session.begin():
            user = session.scalar(select(User).where(User.wa_id == wa_id))
            if user is None:
                user = User(wa_id=wa_id)
                session.add(user)
                session.flush()

            conv = session.scalar(
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.id.desc())
                .limit(1)
            )
            if conv is None:
                conv = Conversation(
                    user_id=user.id,
                    channel="whatsapp",
                    stage="greeting",
                )
                session.add(conv)
                session.flush()

            stage_before = conv.stage

            session.add(
                Message(
                    conversation_id=conv.id,
                    direction="inbound",
                    wam_id=wam_id,
                    body_text=text or None,
                    raw_json=raw_msg,
                )
            )
            conv.last_message_at = datetime.now(timezone.utc)

            has_substance = (
                (msg_type == "text" and (text or "").strip())
                or (msg_type == "interactive" and bool(button_id))
            )
            if stage_before == "greeting" and has_substance:
                conv.stage = "qualification"
            elif (
                stage_before == "qualification"
                and has_substance
                and qualification_satisfied(text, button_id)
            ):
                conv.stage = "proposal"

            conv_id = conv.id

    logger.debug(
        "record_inbound wa_id=%s conv_id=%s stage_before=%s",
        wa_id,
        conv_id,
        stage_before,
    )
    return conv_id, stage_before


def record_outbound(
    database_url: str,
    conversation_id: int,
    body_text: str,
    wam_id: str | None = None,
) -> None:
    sf = _session_factory(database_url)
    with sf() as session:
        with session.begin():
            session.add(
                Message(
                    conversation_id=conversation_id,
                    direction="outbound",
                    wam_id=wam_id,
                    body_text=body_text,
                    raw_json=None,
                )
            )
            conv = session.get(Conversation, conversation_id)
            if conv:
                conv.last_message_at = datetime.now(timezone.utc)
