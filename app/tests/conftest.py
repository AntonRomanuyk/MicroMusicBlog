from collections.abc import AsyncGenerator
from typing import Any, AsyncIterator
import asyncio
import uuid
import pytest
import pytest_asyncio
import asyncpg
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from unittest.mock import AsyncMock

from app.config import settings
from app.database import Base
from app.main import app
from app import models, utils, oauth2


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
    """
    Create the test database if it doesn't exist.
    This runs before any other session-scoped fixtures.
    """
    # Try to connect to system databases to check/create test database
    # We need to connect to a database that exists (postgres, template1, or main db)
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
            f"Could not connect to PostgreSQL. "
            f"Please ensure PostgreSQL is running and credentials are correct."
        )
    
    try:
        # Check if test database exists
        db_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DATABASE_NAME
        )
        
        if not db_exists:
            # Terminate any existing connections to the test database (if any)
            try:
                await conn.execute(
                    f"""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = '{TEST_DATABASE_NAME}' AND pid <> pg_backend_pid()
                    """
                )
            except Exception:
                pass  # Ignore errors if no connections exist
            
            # Create the test database
            # CREATE DATABASE must be executed outside a transaction block
            await conn.execute(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')
    except asyncpg.exceptions.DuplicateDatabaseError:
        # Database already exists (race condition in parallel test runs)
        pass
    except Exception as e:
        raise RuntimeError(
            f"Failed to create test database '{TEST_DATABASE_NAME}': {e}"
        ) from e
    finally:
        await conn.close()
    
    yield
    
    # Optional: Drop test database after all tests (commented out to preserve data)
    # Uncomment the following if you want to clean up after tests:
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
    """
    Async SQLAlchemy engine bound to a separate test database.
    Creates all tables once per test session and disposes the engine at the end.
    """
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
    """
    Session factory bound to the test engine.
    """
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
    """
    Per-test database session.
    Uses a dedicated AsyncSession for each test.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            # Ensure the session is properly closed between tests
            await session.close()

@pytest.fixture(scope="session", autouse=True)
def mock_redis_client() -> AsyncMock:
    from app import redis_client as redis_module
    import app.cache as cache_module
    from app.routers import status as status_router
    import app.main as main_app

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

    # keep every module on the same mock
    redis_module.redis_client = mock
    cache_module.redis_module.redis_client = mock  # type: ignore[attr-defined]
    status_router.redis_module.redis_client = mock  # type: ignore[attr-defined]
    main_app.init_redis = _fake_init_redis
    main_app.close_redis = _fake_close_redis

    return mock


@pytest_asyncio.fixture(scope="session")
async def app_with_overrides(
    async_session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[Any, None]:
    """
    FastAPI app instance with database dependency overridden to use the test session maker.
    """
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
    """
    Async HTTP client bound to the FastAPI app.
    """
    transport = ASGITransport(app=app_with_overrides)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def create_test_user(
    db_session: AsyncSession,
    email: str | None = None,
    password: str = "password123",
    nickname: str | None = None,
) -> models.User:
    """
    Helper function to create a test user with properly hashed password.
    """
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
    """
    Create and persist a test user in the database.
    """
    user = await create_test_user(db_session)
    yield user


@pytest_asyncio.fixture(scope="function")
async def token(test_user: models.User) -> str:
    """
    Generate a valid JWT access token for the test user.
    """
    access_token: str = await oauth2.create_access_token({"user_id": test_user.id})
    return access_token


@pytest_asyncio.fixture(scope="function")
async def authorized_client(
    client: AsyncClient,
    token: str,
) -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient with Authorization header pre-configured.
    """
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client


