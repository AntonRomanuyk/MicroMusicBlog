from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from datetime import datetime, timezone

from starlette.status import HTTP_404_NOT_FOUND, WS_1008_POLICY_VIOLATION, HTTP_401_UNAUTHORIZED

from app.config import settings
from app.database import get_db
from app import models, oauth2
from app.websockets import manager
from app import redis_client as redis_module

router = APIRouter(tags=["status"])

@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=WS_1008_POLICY_VIOLATION)
        return

    try:
        credentials_exception = HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
        token_data = await oauth2.verify_access_token(token, credentials_exception)
        user_id = int(token_data.id)
    except Exception:
        await websocket.close(code=WS_1008_POLICY_VIOLATION)
        return
    await manager.connect(websocket, user_id)
    client = redis_module.redis_client
    if client:
        await client.set(f"user:{user_id}:status", "1", ex=settings.cache_TTL)

    try:
        while True:
            await websocket.receive_text()


    except WebSocketDisconnect:
        await manager.disconnect(websocket, user_id)

        if user_id not in manager.active_connections:

            client = redis_module.redis_client
            if client:
                await client.delete(f"user:{user_id}:status")

            stmt = (
                update(models.User)
                .where(models.User.id == user_id)
                .values(last_seen=datetime.now(timezone.utc))
            )
            await db.execute(stmt)
            await db.commit()

@router.get("/user/{id}/status")
async def get_user_status(id: int, db: AsyncSession = Depends(get_db)):
    is_online = False
    client = redis_module.redis_client
    if client:
        is_online = await client.exists(f"user:{id}:status") > 0

    if is_online:
        return {"is_online": True, "last_seen": None}

    user = await db.get(models.User, id)
    if not user:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")

    return {"is_online": False, "last_seen": user.last_seen}