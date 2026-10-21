"""
WebSocket Connection Manager for real-time safety alert broadcasting.

Broadcasts confirmed safety events, worker tracking statistics,
and job status updates to connected dashboard clients.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections for live alerts."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total clients: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected. Total clients: %d", len(self.active_connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast JSON payload to all connected clients."""
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning("Failed to send message to websocket client: %s", e)
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


# Global singleton manager
ws_manager = ConnectionManager()
ws_router = APIRouter(tags=["websocket"])


@ws_router.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """Real-time event stream endpoint for frontend dashboard."""
    await ws_manager.connect(websocket)
    try:
        # Send initial connection acknowledgment
        await websocket.send_json({
            "type": "CONNECTED",
            "message": "Connected to VisionSafe live event stream",
        })
        while True:
            # Keep connection open, handle pings or client messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug("WebSocket connection closed: %s", e)
        ws_manager.disconnect(websocket)
