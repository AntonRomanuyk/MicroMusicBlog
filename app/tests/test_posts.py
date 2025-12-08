from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.tests.conftest import create_test_user


@pytest.mark.asyncio
async def test_create_post_without_files(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test creating a post without file attachments."""
    post_data = {
        "title": "Test Post",
        "content": "This is a test post content",
        "topic": "technology",
        "published": True,
    }

    response = await authorized_client.post("/posts/create", data=post_data)

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == post_data["title"]
    assert data["content"] == post_data["content"]
    assert data["topic"] == post_data["topic"]
    assert data["published"] == post_data["published"]
    assert data["owner_id"] == test_user.id
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    # Verify post exists in DB
    result = await db_session.execute(select(models.Post).filter(models.Post.id == data["id"]))
    post = result.scalar_one_or_none()
    assert post is not None
    assert post.title == post_data["title"]
    assert post.owner_id == test_user.id


@pytest.mark.asyncio
async def test_create_post_with_files(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test creating a post with file attachments, mocking aiofiles."""
    # Mock aiofiles operations
    mock_file_content = b"fake-file-content"

    def mock_open(file_path: str, mode: str):
        mock_buffer = AsyncMock()
        mock_buffer.write = AsyncMock()
        mock_buffer.__aenter__ = AsyncMock(return_value=mock_buffer)
        mock_buffer.__aexit__ = AsyncMock(return_value=None)
        return mock_buffer

    monkeypatch.setattr("app.routers.post.aiofiles.open", mock_open)
    monkeypatch.setattr("app.routers.post.os.makedirs", lambda *args, **kwargs: None)

    # Use multipart form data - FastAPI expects form fields when files are present
    post_data = {
        "title": "Post with Files",
        "content": "Content with attachments",
        "topic": "music",
        "published": True,
    }

    # Use multipart form data for file upload
    files = [("files", ("test.mp3", mock_file_content, "audio/mpeg"))]

    response = await authorized_client.post(
        "/posts/create",
        data=post_data,
        files=files,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == post_data["title"]
    assert "id" in data

    # Verify post and file exist in DB
    result = await db_session.execute(select(models.Post).filter(models.Post.id == data["id"]))
    post = result.scalar_one_or_none()
    assert post is not None

    file_result = await db_session.execute(
        select(models.PostFile).filter(models.PostFile.post_id == post.id)
    )
    post_files = file_result.scalars().all()
    assert len(post_files) == 1
    assert post_files[0].filename == "test.mp3"


@pytest.mark.asyncio
async def test_update_post_success(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test updating a post - verify only owner can update."""
    # Create a post first
    post = models.Post(
        title="Original Title",
        content="Original content",
        topic="tech",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    update_data = {
        "title": "Updated Title",
        "content": "Updated content",
        "topic": "updated-topic",
        "published": False,
    }

    response = await authorized_client.put(f"/posts/update/id/{post.id}", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == update_data["title"]
    assert data["content"] == update_data["content"]
    assert data["topic"] == update_data["topic"]
    assert data["published"] == update_data["published"]

    # Verify DB state
    await db_session.refresh(post)
    assert post.title == update_data["title"]
    assert post.content == update_data["content"]


@pytest.mark.asyncio
async def test_update_post_unauthorized(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test that non-owner cannot update a post."""
    # Create another user
    other_user = await create_test_user(
        db_session,
        #email="other@example.com",
        #password="password123",
        #nickname="otheruser",
    )

    # Create post owned by other user
    post = models.Post(
        title="Other's Post",
        content="Content",
        published=True,
        owner_id=other_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    update_data = {"title": "Hacked Title", "content": "Hacked", "published": True}

    response = await authorized_client.put(f"/posts/update/id/{post.id}", json=update_data)

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_post_files_unauthorized(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test that non-owner cannot update post files."""
    # Create another user
    other_user = await create_test_user(
        db_session,
        #email="other2@example.com",
        #password="password123",
        #nickname="otheruser2",
    )

    # Create post owned by other user
    post = models.Post(
        title="Other's Post",
        content="Content",
        published=True,
        owner_id=other_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    file_content = b"hacked-content"
    files = [("files", ("hacked.mp3", file_content, "audio/mpeg"))]

    response = await authorized_client.put(
        f"/posts/update/id/{post.id}/files",
        files=files,
    )

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_post_files(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test updating post files - verify only owner can update, mock aiofiles."""
    # Create a post first
    post = models.Post(
        title="Post with Files",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Mock aiofiles operations
    def mock_open(file_path: str, mode: str):
        mock_buffer = AsyncMock()
        mock_buffer.write = AsyncMock()
        mock_buffer.__aenter__ = AsyncMock(return_value=mock_buffer)
        mock_buffer.__aexit__ = AsyncMock(return_value=None)
        return mock_buffer

    mock_exists = AsyncMock(return_value=False)
    mock_remove = AsyncMock()

    monkeypatch.setattr("app.routers.post.aiofiles.open", mock_open)
    monkeypatch.setattr("app.routers.post.aiopath.exists", mock_exists)
    monkeypatch.setattr("app.routers.post.aiofiles.os.remove", mock_remove)

    file_content = b"new-file-content"
    files = [("files", ("new_file.mp3", file_content, "audio/mpeg"))]

    response = await authorized_client.put(
        f"/posts/update/id/{post.id}/files",
        files=files,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == post.id

    # Verify files were updated in DB
    file_result = await db_session.execute(
        select(models.PostFile).filter(models.PostFile.post_id == post.id)
    )
    post_files = file_result.scalars().all()
    assert len(post_files) == 1
    assert post_files[0].filename == "new_file.mp3"


@pytest.mark.asyncio
async def test_get_all_posts_cache_interaction(
    client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
    mock_redis_client: AsyncMock,
) -> None:
    """Test getting all posts and verify cache interaction."""
    # Create a post
    post = models.Post(
        title="Test Post",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()

    initial_get_count = mock_redis_client.get.await_count

    response = await client.get("/posts/all")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(p["id"] == post.id for p in data)

    # Verify cache was accessed
    assert mock_redis_client.get.await_count > initial_get_count


@pytest.mark.asyncio
async def test_get_post_by_id_cache_interaction(
    client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
    mock_redis_client: AsyncMock,
) -> None:
    """Test getting a post by ID and verify cache interaction."""
    post = models.Post(
        title="Single Post",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    initial_get_count = mock_redis_client.get.await_count

    response = await client.get(f"/posts/id/{post.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == post.id
    assert data["title"] == post.title
    assert "owner" in data
    assert data["owner"]["id"] == test_user.id

    # Verify cache was accessed
    assert mock_redis_client.get.await_count > initial_get_count


@pytest.mark.asyncio
async def test_get_post_not_found(client: AsyncClient) -> None:
    """Test getting a non-existent post."""
    response = await client.get("/posts/id/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_post_cascade(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test deleting a post and verify cascade delete logic."""
    # Create a post with a file and comment
    post = models.Post(
        title="Post to Delete",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Add a file
    post_file = models.PostFile(
        filename="test.mp3",
        filepath="/fake/path/test.mp3",
        filetype="audio/mpeg",
        post_id=post.id,
    )
    db_session.add(post_file)

    # Add a comment
    comment = models.Comment(
        content="Test comment",
        post_id=post.id,
        author_id=test_user.id,
    )
    db_session.add(comment)
    await db_session.commit()

    # Mock file operations
    mock_exists = AsyncMock(return_value=False)
    mock_remove = AsyncMock()
    monkeypatch.setattr("app.routers.post.aiopath.exists", mock_exists)
    monkeypatch.setattr("app.routers.post.aiofiles.os.remove", mock_remove)

    response = await authorized_client.delete(f"/posts/delete/id/{post.id}")

    assert response.status_code == 204

    # Verify post is deleted
    result = await db_session.execute(select(models.Post).filter(models.Post.id == post.id))
    deleted_post = result.scalar_one_or_none()
    assert deleted_post is None

    # Verify cascade delete - file should be deleted
    file_result = await db_session.execute(
        select(models.PostFile).filter(models.PostFile.post_id == post.id)
    )
    deleted_files = file_result.scalars().all()
    assert len(deleted_files) == 0

    # Verify cascade delete - comment should be deleted
    comment_result = await db_session.execute(
        select(models.Comment).filter(models.Comment.post_id == post.id)
    )
    deleted_comments = comment_result.scalars().all()
    assert len(deleted_comments) == 0


@pytest.mark.asyncio
async def test_get_all_user_posts_cache_interaction(
    client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
    mock_redis_client: AsyncMock,
) -> None:
    """Test getting all posts by a specific user and verify cache interaction."""
    # Create posts for test_user
    post1 = models.Post(
        title="User Post 1",
        content="Content 1",
        published=True,
        owner_id=test_user.id,
    )
    post2 = models.Post(
        title="User Post 2",
        content="Content 2",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add_all([post1, post2])
    await db_session.commit()

    initial_get_count = mock_redis_client.get.await_count

    response = await client.get(f"/posts/user/{test_user.id}/all")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    assert all(p["owner_id"] == test_user.id for p in data)

    # Verify cache was accessed
    assert mock_redis_client.get.await_count > initial_get_count


@pytest.mark.asyncio
async def test_get_all_user_likes_cache_interaction(
    client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
    mock_redis_client: AsyncMock,
) -> None:
    """Test getting all posts liked by a user and verify cache interaction."""
    # Create another user and their post
    other_user = await create_test_user(
        db_session,
        #email="other3@example.com",
        #password="password123",
        #nickname="otheruser3",
    )

    post = models.Post(
        title="Liked Post",
        content="Content",
        published=True,
        owner_id=other_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Create like relationship
    from sqlalchemy import insert

    await db_session.execute(
        insert(models.post_likes).values(user_id=test_user.id, post_id=post.id)
    )
    post.likes = 1
    await db_session.commit()

    initial_get_count = mock_redis_client.get.await_count

    response = await client.get(f"/posts/user/{test_user.id}/likes")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(p["id"] == post.id for p in data)

    # Verify cache was accessed
    assert mock_redis_client.get.await_count > initial_get_count


@pytest.mark.asyncio
async def test_get_unique_topics_cache_interaction(
    client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
    mock_redis_client: AsyncMock,
) -> None:
    """Test getting unique topics and verify cache interaction."""
    # Create posts with different topics
    post1 = models.Post(
        title="Post 1",
        content="Content",
        topic="technology",
        published=True,
        owner_id=test_user.id,
    )
    post2 = models.Post(
        title="Post 2",
        content="Content",
        topic="music",
        published=True,
        owner_id=test_user.id,
    )
    post3 = models.Post(
        title="Post 3",
        content="Content",
        topic="technology",  # Duplicate topic
        published=True,
        owner_id=test_user.id,
    )
    db_session.add_all([post1, post2, post3])
    await db_session.commit()

    initial_get_count = mock_redis_client.get.await_count

    response = await client.get("/posts/topics")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert "technology" in data
    assert "music" in data
    # Should only have unique topics
    assert len(set(data)) == len(data)

    # Verify cache was accessed
    assert mock_redis_client.get.await_count > initial_get_count


@pytest.mark.asyncio
async def test_delete_post_unauthorized(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test that non-owner cannot delete a post."""
    # Create another user
    other_user = await create_test_user(
        db_session,
        #email="other4@example.com",
        #password="password123",
        #nickname="otheruser4",
    )

    # Create post owned by other user
    post = models.Post(
        title="Other's Post",
        content="Content",
        published=True,
        owner_id=other_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    response = await authorized_client.delete(f"/posts/delete/id/{post.id}")

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]

