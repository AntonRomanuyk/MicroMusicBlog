import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app import utils


@pytest.mark.asyncio
async def test_get_user_by_id_hits_cache(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_redis_client: AsyncMock,
) -> None:
    from app.schemas import UserCreate

    user_in = UserCreate(
        email="cache_user@example.com",
        password="password123",
        nickname="cacheuser",
    )
    hashed = await utils.hash(user_in.password)
    user = models.User(email=user_in.email, password=hashed, nickname=user_in.nickname)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.get(f"/users/id/{user.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == user.id
    assert data["email"] == user.email

    assert mock_redis_client.get.await_count >= 1


@pytest.mark.asyncio
async def test_get_all_users_hits_cache(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_redis_client: AsyncMock,
) -> None:
    from app.schemas import UserCreate

    user_in = UserCreate(
        email="all_users@example.com",
        password="password123",
        nickname="allusers",
    )
    hashed = await utils.hash(user_in.password)
    user = models.User(email=user_in.email, password=hashed, nickname=user_in.nickname)
    db_session.add(user)
    await db_session.commit()

    resp = await client.get("/users/all")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(u["email"] == user_in.email for u in data)
    assert mock_redis_client.get.await_count >= 1


@pytest.mark.asyncio
async def test_update_user_profile(
    authorized_client: AsyncClient,
    db_session: AsyncSession,
    test_user: models.User,
) -> None:
    payload = {"nickname": "updated_nick"}
    resp = await authorized_client.put(f"/users/update/{test_user.id}", json=payload)

    assert resp.status_code == 200
    await db_session.refresh(test_user)
    body = resp.json()
    assert body["nickname"] == "updated_nick"

    updated = await db_session.get(models.User, test_user.id)
    assert updated is not None
    assert updated.nickname == "updated_nick"


@pytest.mark.asyncio
async def test_update_user_avatar(
    authorized_client: AsyncClient,
    db_session: AsyncSession,
    test_user: models.User,
    monkeypatch: Any,
) -> None:
    from app.routers import user as user_router_module

    class DummyAioFile:
        async def __aenter__(self) -> "DummyAioFile":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def write(self, data: bytes) -> None:
            return None

    def fake_open(path: str, mode: str = "rb") -> DummyAioFile:
        return DummyAioFile()

    async def fake_exists(path: str) -> bool:
        return False

    async def fake_remove(path: str) -> None:
        return None

    monkeypatch.setattr(user_router_module.aiofiles, "open", fake_open)
    monkeypatch.setattr(user_router_module.aiopath, "exists", fake_exists)
    monkeypatch.setattr(user_router_module.aiofiles.os, "remove", fake_remove)

    files = {"file": ("avatar.png", b"fake-image-bytes", "image/png")}

    resp = await authorized_client.put(
        f"/users/avatar/update/{test_user.id}",
        files=files,
    )

    assert resp.status_code == 200
    updated = await db_session.get(models.User, test_user.id)
    assert updated is not None


@pytest.mark.asyncio
async def test_update_user_password(
    authorized_client: AsyncClient,
    db_session: AsyncSession,
    test_user: models.User,
) -> None:
    payload = {"current_password": "password123", "new_password": "newpass456"}
    resp = await authorized_client.put(
        f"/users/password/update/{test_user.id}",
        json=payload,
    )

    assert resp.status_code == 200
    await db_session.refresh(test_user)
    updated = await db_session.get(models.User, test_user.id)
    assert updated is not None


@pytest.mark.asyncio
async def test_soft_delete_user_and_cache_invalidation(
    authorized_client: AsyncClient,
    db_session: AsyncSession,
    test_user: models.User,
    mock_redis_client: AsyncMock,
) -> None:
    resp = await authorized_client.delete(f"/users/delete/id/{test_user.id}")

    assert resp.status_code == 204
    await db_session.refresh(test_user)
    await asyncio.sleep(0.1)

    deleted = await db_session.get(models.User, test_user.id)
    assert deleted is not None
    assert deleted.is_deleted is True
    assert deleted.nickname == "Deleted User"

    delete_calls = [call.args[0] for call in mock_redis_client.delete.await_args_list]
    assert "users:all" in delete_calls
    assert f"user:{test_user.id}" in delete_calls
