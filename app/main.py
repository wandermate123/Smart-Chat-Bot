import asyncio
import logging

from fastapi import FastAPI, Request

from app.api.webhooks import whatsapp as whatsapp_api
from app.config import get_settings
from app.db.idempotency import IdempotencyStore
from app.db.engine import ping_database

logger = logging.getLogger(__name__)

_MINIMAL_STATE_FLAG = "_wandermate_minimal_ok"

# Paths that skip app.state entirely (fast probes).
_SKIP_STATE_PATHS = frozenset({"/", "/health"})


def _ensure_minimal_app_state(app: FastAPI) -> None:
    """Settings + idempotency only. Never touches Postgres (webhooks must stay fast)."""
    if getattr(app.state, _MINIMAL_STATE_FLAG, False):
        return
    settings = get_settings()
    if not logging.root.handlers:
        logging.basicConfig(
            level=settings.log_level.upper(),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    app.state.settings = settings
    app.state.idempotency = IdempotencyStore(settings.idempotency_db_path)
    setattr(app.state, _MINIMAL_STATE_FLAG, True)


app = FastAPI(title="WanderMate")
app.include_router(whatsapp_api.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Homepage — API only; WhatsApp webhook is POST /webhooks/whatsapp."""
    s = get_settings()
    return {
        "service": "WanderMate",
        "main_whatsapp_e164": s.main_whatsapp_e164,
        "health": "/health",
        "health_ready": "/health/ready",
        "whatsapp_webhook": "/webhooks/whatsapp",
    }


@app.middleware("http")
async def wandermate_state_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method
    if path in _SKIP_STATE_PATHS:
        return await call_next(request)
    # Meta verify uses get_settings() only; no SQLite / env-heavy init needed.
    if path == "/webhooks/whatsapp" and method == "GET":
        return await call_next(request)
    _ensure_minimal_app_state(request.app)
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> dict[str, str]:
    """Loads settings; pings Postgres if DATABASE_URL is set."""
    settings = get_settings()
    if settings.database_url:
        await asyncio.to_thread(ping_database, settings.database_url)
    return {
        "status": "ready",
        "main_whatsapp_e164": settings.main_whatsapp_e164,
        "database": "ok" if settings.database_url else "disabled",
    }
