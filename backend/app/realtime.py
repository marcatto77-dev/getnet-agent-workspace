import asyncio
from collections import defaultdict
from uuid import uuid4

from fastapi import WebSocket


class RealtimeHub:
    def __init__(self):
        self.customers: dict[str, set[WebSocket]] = defaultdict(set)
        self.technicians: dict[int, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue_positions: dict[str, int] = {}

    @staticmethod
    def event(event_type: str, **payload) -> dict:
        return {"event_id": str(uuid4()), "type": event_type, **payload}

    def bind(self):
        self.loop = asyncio.get_running_loop()

    async def add_customer(self, conversation_id: str, websocket: WebSocket):
        await websocket.accept()
        self.customers[conversation_id].add(websocket)

    async def add_technician(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.technicians[user_id].add(websocket)

    def remove_customer(self, conversation_id: str, websocket: WebSocket):
        self.customers[conversation_id].discard(websocket)

    def remove_technician(self, user_id: int, websocket: WebSocket) -> bool:
        self.technicians[user_id].discard(websocket)
        return not self.technicians[user_id]

    async def _send(self, sockets: set[WebSocket], event: dict):
        stale = []
        for socket in tuple(sockets):
            try:
                await socket.send_json(event)
            except Exception:
                stale.append(socket)
        for socket in stale:
            sockets.discard(socket)

    async def customer(self, conversation_id: str, event: dict):
        await self._send(self.customers[conversation_id], event)

    async def technician(self, user_id: int, event: dict):
        await self._send(self.technicians[user_id], event)

    async def all_technicians(self, event: dict):
        for sockets in tuple(self.technicians.values()):
            await self._send(sockets, event)

    def publish_customer(self, conversation_id: str, event: dict):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.customer(conversation_id, event), self.loop)

    def publish_technician(self, user_id: int, event: dict):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.technician(user_id, event), self.loop)

    def publish_all_technicians(self, event: dict):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.all_technicians(event), self.loop)


hub = RealtimeHub()
