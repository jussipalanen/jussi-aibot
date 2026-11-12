"""
ASGI entry point: `uvicorn main:app`.
"""
from aibot.app import create_app
from aibot.settings import configure_logging

configure_logging()
app = create_app()
