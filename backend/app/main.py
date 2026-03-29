"""SegmentIQ FastAPI Application."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncio
import json

from app.api.routes import router
from app.config import get_settings
from app.storage.dynamodb import ensure_table_exists

LOCAL_UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "local_uploads")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure local storage dirs exist
    os.makedirs(LOCAL_UPLOADS_DIR, exist_ok=True)
    # Ensure DB table exists
    try:
        ensure_table_exists()
        logger.info("Storage ready")
    except Exception as e:
        logger.warning(f"Storage setup warning: {e}")
    yield


app = FastAPI(
    title="SegmentIQ API",
    description="AI-powered video segmentation using TwelveLabs Marengo + Pegasus via AWS Bedrock",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins = [o.strip() for o in settings.cors_origins.split(",")]
# Allow wildcard when CORS_ORIGINS=* (useful for dev/staging)
if cors_origins == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(router, prefix="/api")

# Serve locally stored videos and filmstrip frames at /local-files/
os.makedirs(LOCAL_UPLOADS_DIR, exist_ok=True)
app.mount("/local-files", StaticFiles(directory=LOCAL_UPLOADS_DIR), name="local-files")


# WebSocket progress endpoint
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, video_id: str, websocket: WebSocket):
        await websocket.accept()
        if video_id not in self.active_connections:
            self.active_connections[video_id] = []
        self.active_connections[video_id].append(websocket)

    def disconnect(self, video_id: str, websocket: WebSocket):
        if video_id in self.active_connections:
            self.active_connections[video_id].remove(websocket)

    async def broadcast(self, video_id: str, message: dict):
        if video_id in self.active_connections:
            dead = []
            for ws in self.active_connections[video_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.active_connections[video_id].remove(ws)


manager = ConnectionManager()


@app.websocket("/ws/videos/{video_id}/progress")
async def websocket_progress(websocket: WebSocket, video_id: str):
    """WebSocket endpoint for real-time pipeline progress."""
    await manager.connect(video_id, websocket)
    from app.storage.dynamodb import get_video_record

    try:
        # Poll DynamoDB every 2 seconds and push updates
        last_status = None
        while True:
            record = get_video_record(video_id)
            if record:
                current_status = f"{record.get('status')}:{record.get('progress')}"
                if current_status != last_status:
                    await websocket.send_json({
                        "video_id": video_id,
                        "status": record.get("status"),
                        "progress": record.get("progress", 0),
                        "error": record.get("error"),
                    })
                    last_status = current_status

                    if record.get("status") in ("complete", "failed"):
                        break

            await asyncio.sleep(2)
    except WebSocketDisconnect:
        manager.disconnect(video_id, websocket)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "segmentiq-api"}
