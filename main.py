"""
ASGI entry point: `uvicorn main:app`.
"""
from aibot.app import create_app

app = create_app()
