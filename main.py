"""
Jussi AI Bot - Finnish Resume Review Service
Main application entry point with model initialization.
"""
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import os

from routes import router, limiter

app = FastAPI(
    title="Jussi AI Bot",
    version="0.1.0",
    description="A simple AI bot built with FastAPI and PyTorch for Finnish resume analysis."
)

# Configure CORS for allowed origins
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def add_robots_header(request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
    return response

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routes
app.include_router(router)