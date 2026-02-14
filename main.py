"""
Main application entry point for Cursed Mounds backend.

This file replicates the upstream ``main.py`` but adds a small guard around
the static file mounting.  The original project attempted to mount a
``static`` directory for hosting terms/privacy pages directly at runtime.
However, when the directory is missing (for example in a fresh deployment
or development container), ``starlette.staticfiles.StaticFiles`` will raise
``RuntimeError: Directory 'static' does not exist`` and crash the entire
application.  To avoid this crash while still serving static assets when
they are present, this version checks for the existence of the directory
before mounting it.  If the directory is absent the application will
simply log a message and continue without static file hosting.
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import socketio

from config import settings
from database import init_db, close_db
from redis_client import init_redis, close_redis
from services.live_ops import live_ops
from services.analytics import analytics
from routers import auth, game, shop, guild, boss, social, health

# Create Socket.IO server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.WEBSOCKET_CORS_ALLOWED_ORIGINS,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await init_db()
    await init_redis()

    # Start background tasks
    asyncio.create_task(weekly_cycle_task())
    asyncio.create_task(analytics_flush_task())

    yield

    # Shutdown
    await close_db()
    await close_redis()


async def weekly_cycle_task():
    """Background task for weekly LiveOps."""
    while True:
        try:
            await live_ops.process_weekly_cycle()
        except Exception as e:  # pylint: disable=broad-except
            # Log exception but keep the loop alive
            print(f"Weekly cycle error: {e}")
        await asyncio.sleep(3600)  # Check every hour


async def analytics_flush_task():
    """Background task to flush analytics buffer."""
    while True:
        await asyncio.sleep(60)  # Every minute
        try:
            await analytics._flush_buffer()  # pylint: disable=protected-access
        except Exception as e:  # pylint: disable=broad-except
            print(f"Analytics flush error: {e}")


# Create FastAPI app
app = FastAPI(
    title="Cursed Mounds API",
    description="Ethno-Ukrainian real-time game API",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
if settings.ENVIRONMENT == "development":
    cors_origins: list[str] = ["*"]
else:
    cors_origins = []
    if settings.FRONTEND_ORIGIN:
        cors_origins.append(settings.FRONTEND_ORIGIN)

    # Allow additional origins via env (comma-separated)
    extra = settings.WEBSOCKET_CORS_ALLOWED_ORIGINS or []
    if "*" in extra:
        cors_origins = ["*"]
    else:
        cors_origins.extend([o for o in extra if o and o not in cors_origins])

# NOTE: allow_credentials can't be True when allow_origins is ["*"]
allow_credentials = cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(game.router, prefix="/api/game", tags=["game"])
app.include_router(shop.router, prefix="/api/shop", tags=["shop"])
app.include_router(guild.router, prefix="/api/guild", tags=["guild"])
app.include_router(boss.router, prefix="/api/boss", tags=["boss"])
app.include_router(social.router, prefix="/api/social", tags=["social"])

# Static files (for terms/privacy)
# Use absolute path relative to this file to avoid missing directory errors.
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    # If the directory exists, mount it so that terms/privacy pages are served.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    # Otherwise, log a message; do not raise an exception that would crash the app.
    print(
        f"Warning: Static directory not found at {STATIC_DIR}. "
        "Terms/privacy pages will not be served."
    )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint for health check."""
    return {
        "name": "Cursed Mounds API",
        "version": "2.0.0",
        "status": "operational",
        "environment": settings.ENVIRONMENT,
    }


# Socket.IO events
@sio.event
async def connect(sid: str, environ: dict) -> None:
    print(f"Client connected: {sid}")


@sio.event
async def disconnect(sid: str) -> None:
    print(f"Client disconnected: {sid}")


# Mount Socket.IO
app.mount("/socket.io", socketio.ASGIApp(sio))
