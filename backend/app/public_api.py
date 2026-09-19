"""Free backend host: API and sandboxed documents, separate from the web origin.

The frontend proxies authenticated requests; refresh cookies belong to that
frontend host. Published document code always runs in an opaque sandbox.
"""
from .main import create_app
from .site_server import router

app = create_app()
app.include_router(router)
