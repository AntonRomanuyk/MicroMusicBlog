import asyncio
import uuid
from collections.abc import AsyncGenerator
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import models
from app import oauth2
from app import utils
from app.config import settings
from app.database import Base
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


TEST_DATABASE_NAME: str = f"{settings.database_name}_test"
TEST_DATABASE_URL: str = (
    f"postgresql+asyncpg://{settings.database_user}:{settings.database_password}"
    f"@{settings.database_hostname}:{settings.database_port}/{TEST_DATABASE_NAME}"
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_test_database() -> AsyncGenerator[None, None]:
    conn = None
    for db_name in ["postgres", "template1", settings.database_name]:
        try:
            conn = await asyncpg.connect(
                host=settings.database_hostname,
                port=int(settings.database_port),
                user=settings.database_user,
                password=settings.database_password,
                database=db_name,
            )
            break
        except Exception:
            continue

    if conn is None:
        raise RuntimeError(
            "Could not connect to PostgreSQL. Please ensure PostgreSQL is running and credentials are correct."
        )

    try:
        db_exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DATABASE_NAME)

        if not db_exists:
            try:
                await conn.execute(
                    f"""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = '{TEST_DATABASE_NAME}' AND pid <> pg_backend_pid()
                    """
                )
            except Exception:
                pass

            await conn.execute(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')
    except asyncpg.exceptions.DuplicateDatabaseError:
        pass
    except Exception as e:
        raise RuntimeError(f"Failed to create test database '{TEST_DATABASE_NAME}': {e}") from e
    finally:
        await conn.close()

    yield

    for db_name in ["postgres", "template1", settings.database_name]:
        try:
            conn = await asyncpg.connect(
                host=settings.database_hostname,
                port=int(settings.database_port),
                user=settings.database_user,
                password=settings.database_password,
                database=db_name,
            )
            await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}"')
            await conn.close()
            break
        except Exception:
            continue


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine: AsyncEngine = create_async_engine(
        TEST_DATABASE_URL,
        future=True,
        echo=False,
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def async_session_maker(
    test_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield maker


@pytest_asyncio.fixture(scope="function")
async def db_session(
    async_session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture(scope="session", autouse=True)
def mock_redis_client() -> AsyncMock:
    import app.cache as cache_module
    import app.main as main_app
    from app import redis_client as redis_module
    from app.routers import status as status_router

    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.exists = AsyncMock(return_value=0)
    mock.aclose = AsyncMock(return_value=None)

    async def _fake_init_redis() -> None:
        redis_module.redis_client = mock

    async def _fake_close_redis() -> None:
        return None

    redis_module.redis_client = mock
    cache_module.redis_module.redis_client = mock
    status_router.redis_module.redis_client = mock
    main_app.init_redis = _fake_init_redis
    main_app.close_redis = _fake_close_redis

    return mock


@pytest_asyncio.fixture(scope="session")
async def app_with_overrides(
    async_session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[Any, None]:
    from app.database import get_db as original_get_db

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with async_session_maker() as session:
            yield session

    app.dependency_overrides[original_get_db] = override_get_db

    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def client(app_with_overrides: Any) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app_with_overrides)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def create_test_user(
    db_session: AsyncSession,
    email: str | None = None,
    password: str = "password123",
    nickname: str | None = None,
) -> models.User:
    if email is None:
        email = f"test_{uuid.uuid4().hex}@example.com"
    if nickname is None:
        nickname = f"user_{uuid.uuid4().hex[:8]}"

    hashed_password: str = await utils.hash(password)
    user = models.User(
        email=email,
        password=hashed_password,
        nickname=nickname,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> AsyncGenerator[models.User, None]:
    user = await create_test_user(db_session)
    yield user


@pytest_asyncio.fixture(scope="function")
async def token(test_user: models.User) -> str:
    access_token: str = await oauth2.create_access_token({"user_id": test_user.id})
    return access_token


@pytest_asyncio.fixture(scope="function")
async def authorized_client(
    client: AsyncClient,
    token: str,
) -> AsyncGenerator[AsyncClient, None]:
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client
