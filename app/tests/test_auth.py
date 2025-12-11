import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.schemas import UserCreate
from app.utils import hash as hash_password


@pytest.mark.asyncio
async def test_login_success(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    password = "password123"
    user_in = UserCreate(email="login_success@example.com", password=password, nickname="loginuser")
    hashed = await hash_password(user_in.password)
    user = models.User(email=user_in.email, password=hashed, nickname=user_in.nickname)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post(
        "/login",
        data={"username": user_in.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    password = "correct-password"
    user_in = UserCreate(email="wrong_pwd@example.com", password=password, nickname="wrongpwd")
    hashed = await hash_password(user_in.password)
    user = models.User(email=user_in.email, password=hashed, nickname=user_in.nickname)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post(
        "/login",
        data={"username": user_in.email, "password": "incorrect"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_register_user_and_persist(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = {
        "email": "register@example.com",
        "password": "password123",
        "nickname": "registeruser",
    }
    resp = await client.post("/users/create", json=payload)

    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == payload["email"]
    assert data["nickname"] == payload["nickname"]
    assert "id" in data

    created = await db_session.get(models.User, data["id"])
    assert created is not None
    assert created.email == payload["email"]


@pytest.mark.asyncio
async def test_register_duplicate_email(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = {
        "email": "dup@example.com",
        "password": "password123",
        "nickname": "dupuser1",
    }
    resp1 = await client.post("/users/create", json=payload)
    assert resp1.status_code == 201

    payload2 = {
        "email": "dup@example.com",
        "password": "password456",
        "nickname": "dupuser2",
    }
    resp2 = await client.post("/users/create", json=payload2)

    assert resp2.status_code == 400
    body = resp2.json()
    assert "email" in body["detail"].lower() or "exists" in body["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_token_flow(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    password = "password123"
    user_in = UserCreate(email="refresh@example.com", password=password, nickname="refreshuser")
    hashed = await hash_password(user_in.password)
    user = models.User(email=user_in.email, password=hashed, nickname=user_in.nickname)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    login_resp = await client.post(
        "/login",
        data={"username": user_in.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    refresh_token = tokens["refresh_token"]

    refresh_resp = await client.post("/refresh", json={"refresh_token": refresh_token})

    assert refresh_resp.status_code == 200
    body = refresh_resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
