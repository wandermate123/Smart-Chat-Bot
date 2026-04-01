import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.webhooks import whatsapp as whatsapp_api
from app.config import Settings, get_settings
from app.db.idempotency import IdempotencyStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app.state.settings = settings
    app.state.idempotency = IdempotencyStore(settings.idempotency_db_path)
    yield


app = FastAPI(title="WanderMate", lifespan=lifespan)
app.include_router(whatsapp_api.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
