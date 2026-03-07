"""
Jussi AI Bot - Finnish Resume Review Service
Main application entry point with model initialization.
"""
from fastapi import FastAPI, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from routes import router, limiter

app = FastAPI(
    title="Jussi AI Bot",
    version="0.1.0",
    description="A simple AI bot built with FastAPI and PyTorch for Finnish resume analysis."
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