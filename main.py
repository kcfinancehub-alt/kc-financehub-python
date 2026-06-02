"""Entry point shim — the real application lives in app.py.

This file exists so tools that expect a `main:app` import path work correctly.
Import and re-export the FastAPI application from app.py to avoid duplicate
app instances.
"""

from app import app  # noqa: F401  — re-exported for Gunicorn / uvicorn

__all__ = ["app"]