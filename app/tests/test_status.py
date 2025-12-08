"""
WebSocket Status Feature Tests (httpx_ws)
"""
from datetime import datetime, timezone
import asyncio
from typing import Any
from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.websockets import manager


def _active_key(user_id: int):
    if user_id in manager.active_connections:
        return user_id
    user_str = str(user_id)
    if user_str in manager.active_connections:
        return user_str
    return None


@asynccontextmanager
async def _ws_client(app: Any) -> AsyncClient:
    transport = ASGIWebSocketTransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_websocket_connection_success(
    client: AsyncClient,
    test_user: models.User,
    token: str,
    app_with_overrides: Any,
) -> None:
    manager.active_connections.clear()
    async with _ws_client(app_with_overrides) as ws_client:
        async with aconnect_ws(f"/ws/status?token={token}", client=ws_client):
            user_key = _active_key(test_user.id)
            assert user_key is not None
            assert len(manager.active_connections[user_key]) == 1


@pytest.mark.asyncio
async def test_websocket_online_status_redis_set(
    client: AsyncClient,
    token: str,
    mock_redis_client: AsyncMock,
    app_with_overrides: Any,
) -> None:
    manager.active_connections.clear()
    mock_redis_client.set.reset_mock()

    async with _ws_client(app_with_overrides) as ws_client:
        async with aconnect_ws(f"/ws/status?token={token}", client=ws_client):
            pass

    assert mock_redis_client.set.await_count >= 1
    key, value = mock_redis_client.set.await_args_list[-1][0][:2]
    assert key.endswith(":status")
    assert value == "1"


@pytest.mark.asyncio
async def test_websocket_disconnection_redis_delete_and_last_seen(
    client: AsyncClient,
    test_user: models.User,
    token: str,
    mock_redis_client: AsyncMock,
    db_session: AsyncSession,
    app_with_overrides: Any,
) -> None:
    manager.active_connections.clear()
    mock_redis_client.delete.reset_mock()

    # Ensure last_seen is None
    test_user.last_seen = None
    await db_session.commit()
    await db_session.refresh(test_user)

    async with _ws_client(app_with_overrides) as ws_client:
        async with aconnect_ws(f"/ws/status?token={token}", client=ws_client):
            pass

    # Allow the disconnect handler to run
    await asyncio.sleep(0.3)

    # Redis delete called
    assert mock_redis_client.delete.await_count >= 1
    del_key = mock_redis_client.delete.await_args_list[-1][0][0]
    assert del_key == f"user:{test_user.id}:status"

    # last_seen updated
    await db_session.refresh(test_user)
    assert test_user.last_seen is not None
    assert isinstance(test_user.last_seen, datetime)


@pytest.mark.asyncio
async def test_websocket_invalid_token_missing(
    client: AsyncClient,
    app_with_overrides: Any,
) -> None:
    manager.active_connections.clear()
    with pytest.raises(Exception):
        async with _ws_client(app_with_overrides) as ws_client:
            async with aconnect_ws("/ws/status", client=ws_client):
                pass


@pytest.mark.asyncio
async def test_websocket_invalid_token_invalid_format(
    client: AsyncClient,
    app_with_overrides: Any,
) -> None:
    manager.active_connections.clear()
    with pytest.raises(Exception):
        async with _ws_client(app_with_overrides) as ws_client:
            async with aconnect_ws("/ws/status?token=invalid.token", client=ws_client):
                pass


@pytest.mark.asyncio
async def test_websocket_multiple_connections_same_user(
    client: AsyncClient,
    test_user: models.User,
    token: str,
    app_with_overrides: Any,
) -> None:
    manager.active_connections.clear()
    async with _ws_client(app_with_overrides) as ws_client_outer:
        async with aconnect_ws(f"/ws/status?token={token}", client=ws_client_outer):
            user_key = _active_key(test_user.id)
            assert user_key is not None
            assert len(manager.active_connections[user_key]) == 1

            # Use a separate WS client for the second connection to avoid reuse issues
            async with _ws_client(app_with_overrides) as ws_client_inner:
                async with aconnect_ws(
                    f"/ws/status?token={token}", client=ws_client_inner
                ):
                    assert len(manager.active_connections[user_key]) == 2

            # After inner disconnect
            assert len(manager.active_connections[user_key]) == 1

        # After outer disconnect
        assert user_key not in manager.active_connections


@pytest.mark.asyncio
async def test_websocket_last_seen_updates_only_when_no_connections(
    client: AsyncClient,
    test_user: models.User,
    token: str,
    db_session: AsyncSession,
    app_with_overrides: Any,
) -> None:
    manager.active_connections.clear()
    initial_last_seen = datetime(2020, 1, 1, tzinfo=timezone.utc)
    test_user.last_seen = initial_last_seen
    await db_session.commit()
    await db_session.refresh(test_user)

    user_key = test_user.id
    # First connection
    async with _ws_client(app_with_overrides) as ws_client:
        async with aconnect_ws(f"/ws/status?token={token}", client=ws_client):
            # Second connection
            async with aconnect_ws(f"/ws/status?token={token}", client=ws_client):
                pass
            # Still connected (first)
            await db_session.refresh(test_user)
            assert test_user.last_seen == initial_last_seen

    # After all disconnected
    await db_session.refresh(test_user)
    await asyncio.sleep(0.3)
    assert test_user.last_seen is not None
    assert test_user.last_seen != initial_last_seen


@pytest.mark.asyncio
async def test_get_user_status_online(
    client: AsyncClient,
    test_user: models.User,
    token: str,
    mock_redis_client: AsyncMock,
    app_with_overrides: Any,
) -> None:
    manager.active_connections.clear()
    mock_redis_client.exists = AsyncMock(return_value=1)
    async with _ws_client(app_with_overrides) as ws_client:
        async with aconnect_ws(f"/ws/status?token={token}", client=ws_client):
            response = await client.get(f"/user/{test_user.id}/status")
            assert response.status_code == 200
            data = response.json()
            assert data["is_online"] is True
            assert data["last_seen"] is None


@pytest.mark.asyncio
async def test_get_user_status_offline(
    client: AsyncClient,
    test_user: models.User,
    mock_redis_client: AsyncMock,
    db_session: AsyncSession,
    app_with_overrides: Any,
) -> None:
    manager.active_connections.clear()
    mock_redis_client.exists = AsyncMock(return_value=0)
    test_user.last_seen = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    await db_session.commit()

    response = await client.get(f"/user/{test_user.id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["is_online"] is False
    assert data["last_seen"] is not None


@pytest.mark.asyncio
async def test_get_user_status_not_found(
    client: AsyncClient,
    mock_redis_client: AsyncMock,
    app_with_overrides: Any,
) -> None:
    mock_redis_client.exists = AsyncMock(return_value=0)
    response = await client.get("/user/99999/status")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

