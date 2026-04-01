"""Vercel serverless entry — must live under /api (see Vercel Functions layout)."""

from app.main import app

__all__ = ["app"]
