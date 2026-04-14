import asyncio
import logging

from fastapi import FastAPI, Request

from app.api.webhooks import whatsapp as whatsapp_api
from app.config import get_settings
from app.db.engine import init_engine_and_tables, ping_database
from app.db.idempotency import IdempotencyStore

logger = logging.getLogger(__name__)

_STATE_FLAG = "_wandermate_state_ok"


def _ensure_app_state(app: FastAPI) -> None:
    if getattr(app.state, _STATE_FLAG, False):
        return
    settings = get_settings()
    if not logging.root.handlers:
        logging.basicConfig(
            level=settings.log_level.upper(),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    app.state.settings = settings
    app.state.idempotency = IdempotencyStore(settings.idempotency_db_path)
    if (
        settings.database_url
        and not getattr(app.state, "_db_schema_ok", False)
        and not getattr(app.state, "_db_init_attempted", False)
    ):
        app.state._db_init_attempted = True
        try:
            if settings.database_auto_create_tables:
                init_engine_and_tables(settings.database_url)
            else:
                ping_database(settings.database_url)
            app.state._db_schema_ok = True
        except Exception:
            logger.exception("Postgres init / ping failed")
    setattr(app.state, _STATE_FLAG, True)


# Skip loading secrets / SQLite for simple probes (e.g. Vercel, uptime checks)
_SKIP_STATE_PATHS = frozenset({"/", "/health"})


def _needs_full_app_state(request: Request) -> bool:
    if request.url.path in _SKIP_STATE_PATHS:
        return False
    # Meta webhook *verification* is GET-only: needs token compare only, not SQLite.
    if request.url.path == "/webhooks/whatsapp" and request.method == "GET":
        return False
    return True


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
    if _needs_full_app_state(request):
        _ensure_app_state(request.app)
    response = await call_next(request)
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> dict[str, str]:
    """Loads settings + SQLite idempotency; pings Postgres if DATABASE_URL is set."""
    settings = get_settings()
    if settings.database_url:
        await asyncio.to_thread(ping_database, settings.database_url)
    return {
        "status": "ready",
        "main_whatsapp_e164": settings.main_whatsapp_e164,
        "database": "ok" if settings.database_url else "disabled",
    }
