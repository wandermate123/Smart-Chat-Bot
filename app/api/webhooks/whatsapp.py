import json
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import Settings
from app.core.security import verify_meta_signature
from app.db.idempotency import IdempotencyStore
from app.services.inbound_processor import process_whatsapp_payload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp"])


@router.get("/webhooks/whatsapp")
async def whatsapp_verify(
    request: Request,
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> PlainTextResponse:
    settings: Settings = request.app.state.settings
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        if hub_challenge is None:
            raise HTTPException(status_code=400, detail="Missing hub.challenge")
        return PlainTextResponse(content=hub_challenge)
    logger.warning("Webhook verify failed: mode=%r", hub_mode)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhooks/whatsapp")
async def whatsapp_inbound(request: Request) -> dict[str, bool]:
    raw = await request.body()
    settings: Settings = request.app.state.settings
    sig = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(raw, sig, settings.meta_app_secret):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    idempotency: IdempotencyStore = request.app.state.idempotency
    # Await on serverless (e.g. Vercel): background work after response may not run.
    await process_whatsapp_payload(payload, settings, idempotency)
    return {"ok": True}
