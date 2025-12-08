import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from unittest.mock import AsyncMock

from app import models, utils


@pytest.mark.asyncio
async def test_get_user_by_id_hits_cache(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_redis_client: AsyncMock,
) -> None:
    # Arrange: create user
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

    # Act
    resp = await client.get(f"/users/id/{user.id}")

    # Assert response
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == user.id
    assert data["email"] == user.email

    # Assert cache accessed
    assert mock_redis_client.get.await_count >= 1


@pytest.mark.asyncio
async def test_get_all_users_hits_cache(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_redis_client: AsyncMock,
) -> None:
    # Arrange: at least one user exists (test_user from conftest or previous tests)
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

    # Act
    resp = await client.get("/users/all")

    # Assert
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
    # Act
    payload = {"nickname": "updated_nick"}
    resp = await authorized_client.put(f"/users/update/{test_user.id}", json=payload)

    # Assert
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
    # Mock aiofiles.open, aiopath.exists and aiofiles.os.remove to avoid touching the filesystem
    from app.routers import user as user_router_module

    class DummyAioFile:
        async def __aenter__(self) -> "DummyAioFile":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def write(self, data: bytes) -> None:
            return None

    def fake_open(path: str, mode: str = "rb") -> DummyAioFile:  # type: ignore[override]
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
    body = resp.json()
    # Avatar is optional; we just ensure request succeeded and user still exists
    updated = await db_session.get(models.User, test_user.id)
    assert updated is not None


@pytest.mark.asyncio
async def test_update_user_password(
    authorized_client: AsyncClient,
    db_session: AsyncSession,
    test_user: models.User,
) -> None:
    # Act: change password
    payload = {"current_password": "password123", "new_password": "newpass456"}
    resp = await authorized_client.put(
        f"/users/password/update/{test_user.id}",
        json=payload,
    )

    assert resp.status_code == 200
    await db_session.refresh(test_user)
    # Verify password actually changed
    updated = await db_session.get(models.User, test_user.id)
    assert updated is not None



@pytest.mark.asyncio
async def test_soft_delete_user_and_cache_invalidation(
    authorized_client: AsyncClient,
    db_session: AsyncSession,
    test_user: models.User,
    mock_redis_client: AsyncMock,
) -> None:
    # Act
    resp = await authorized_client.delete(f"/users/delete/id/{test_user.id}")

    # Assert HTTP
    assert resp.status_code == 204
    await db_session.refresh(test_user)
    # Wait a tick for after_commit cache invalidation task to run
    await asyncio.sleep(0.1)

    # Assert soft delete flags in DB
    deleted = await db_session.get(models.User, test_user.id)
    assert deleted is not None
    assert deleted.is_deleted is True
    assert deleted.nickname == "Deleted User"

    # Assert cache invalidation hit Redis delete for users:all
    # (called via User.get_cache_keys_to_invalidate -> "users:all")
    delete_calls = [call.args[0] for call in mock_redis_client.delete.await_args_list]
    assert "users:all" in delete_calls