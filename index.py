"""Vercel serverless entrypoint — re-exports the FastAPI app (see Vercel FastAPI docs)."""

from app.main import app

__all__ = ["app"]
