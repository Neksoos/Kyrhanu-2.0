"""
Main application entry point for Cursed Mounds backend.
"""
import asyncio
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
    async_mode='asgi',
    cors_allowed_origins=settings.WEBSOCKET_CORS_ALLOWED_ORIGINS
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
        except Exception as e:
            print(f"Weekly cycle error: {e}")
        await asyncio.sleep(3600)  # Check every hour


async def analytics_flush_task():
    """Background task to flush analytics buffer."""
    while True:
        await asyncio.sleep(60)  # Every minute
        try:
            await analytics._flush_buffer()
        except Exception as e:
            print(f"Analytics flush error: {e}")


# Create FastAPI app
app = FastAPI(
    title="Cursed Mounds API",
    description="Ethno-Ukrainian real-time game API",
    version="2.0.0",
    lifespan=lifespan
)

# CORS
# We mainly use Bearer tokens (Authorization header), not cookies.
# In production allow your frontend origin(s) via WEBSOCKET_CORS_ALLOWED_ORIGINS,
# plus Telegram domains for embedded WebApps.
cors_base = {
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}

if settings.ENVIRONMENT == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        **cors_base,
    )
else:
    allowed = settings.WEBSOCKET_CORS_ALLOWED_ORIGINS
    if "*" in allowed:
        # Avoid invalid combination "*" + credentials.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_origin_regex=r"^https:\/\/([a-z0-9-]+\.)*(telegram\.org|t\.me)$",
            **cors_base,
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed,
            allow_credentials=True,
            allow_origin_regex=r"^https:\/\/([a-z0-9-]+\.)*(telegram\.org|t\.me)$",
            **cors_base,
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
from pathlib import Path
if Path('static').is_dir():
    app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get("/")
async def root():
    return {
        "name": "Cursed Mounds API",
        "version": "2.0.0",
        "status": "operational",
        "environment": settings.ENVIRONMENT
    }


# Socket.IO events
@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")


# Mount Socket.IO
app.mount("/socket.io", socketio.ASGIApp(sio))