"""
Jussi AI Bot - Finnish Resume Review Service
Main application entry point with model initialization.
"""
from fastapi import FastAPI

from routes import router

app = FastAPI(
    title="Jussi AI Bot",
    version="0.1.0",
    description="A simple AI bot built with FastAPI and PyTorch for Finnish resume analysis."
)

# Include routes
app.include_router(router)