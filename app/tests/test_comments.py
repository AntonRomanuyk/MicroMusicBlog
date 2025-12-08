import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.tests.conftest import create_test_user


@pytest.mark.asyncio
async def test_add_comment_to_post(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test adding a comment to a post."""
    # Create a post
    post = models.Post(
        title="Post for Comments",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    comment_data = {"content": "This is a test comment"}

    response = await authorized_client.post(
        f"/posts/{post.id}/comment",
        json=comment_data,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["content"] == comment_data["content"]
    assert data["author_id"] == test_user.id
    assert "id" in data
    assert "created_at" in data

    # Verify comment exists in DB
    result = await db_session.execute(
        select(models.Comment).filter(models.Comment.id == data["id"])
    )
    comment = result.scalar_one_or_none()
    assert comment is not None
    assert comment.content == comment_data["content"]
    assert comment.post_id == post.id
    assert comment.author_id == test_user.id


@pytest.mark.asyncio
async def test_add_comment_to_nonexistent_post(
    authorized_client: AsyncClient,
) -> None:
    """Test adding a comment to a non-existent post."""
    comment_data = {"content": "This comment won't work"}

    response = await authorized_client.post("/posts/99999/comment", json=comment_data)

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_comment_success(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test deleting a comment - verify permissions."""
    # Create a post
    post = models.Post(
        title="Post with Comment",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Create a comment
    comment = models.Comment(
        content="Comment to delete",
        post_id=post.id,
        author_id=test_user.id,
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    response = await authorized_client.delete(f"/posts/comment/{comment.id}")

    assert response.status_code == 204

    # Verify comment is deleted from DB
    result = await db_session.execute(
        select(models.Comment).filter(models.Comment.id == comment.id)
    )
    deleted_comment = result.scalar_one_or_none()
    assert deleted_comment is None


@pytest.mark.asyncio
async def test_delete_comment_unauthorized(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test that non-author cannot delete a comment."""
    # Create another user
    other_user = await create_test_user(
        db_session,
        email="other@example.com",
        password="password123",
        nickname="otheruser",
    )

    # Create a post
    post = models.Post(
        title="Post",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Create a comment by other user
    comment = models.Comment(
        content="Other's comment",
        post_id=post.id,
        author_id=other_user.id,
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    # Try to delete as test_user (not the author)
    response = await authorized_client.delete(f"/posts/comment/{comment.id}")

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]

    # Verify comment still exists
    result = await db_session.execute(
        select(models.Comment).filter(models.Comment.id == comment.id)
    )
    existing_comment = result.scalar_one_or_none()
    assert existing_comment is not None


@pytest.mark.asyncio
async def test_delete_nonexistent_comment(
    authorized_client: AsyncClient,
) -> None:
    """Test deleting a non-existent comment."""
    response = await authorized_client.delete("/posts/comment/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_comment_success(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test updating a comment on a post."""
    # Create a post
    post = models.Post(
        title="Post",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Create a comment
    comment = models.Comment(
        content="Original comment",
        post_id=post.id,
        author_id=test_user.id,
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    update_data = {"content": "Updated comment content"}

    response = await authorized_client.put(
        f"/posts/comment/{comment.id}",
        json=update_data,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == update_data["content"]
    assert data["id"] == comment.id

    # Verify DB state
    await db_session.refresh(comment)
    assert comment.content == update_data["content"]


@pytest.mark.asyncio
async def test_update_comment_unauthorized(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test that non-author cannot update a comment."""
    # Create another user
    other_user = await create_test_user(
        db_session,
        email="other2@example.com",
        password="password123",
        nickname="otheruser2",
    )

    # Create a post
    post = models.Post(
        title="Post",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Create a comment by other user
    comment = models.Comment(
        content="Other's comment",
        post_id=post.id,
        author_id=other_user.id,
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)

    update_data = {"content": "Hacked content"}

    # Try to update as test_user (not the author)
    response = await authorized_client.put(
        f"/posts/comment/{comment.id}",
        json=update_data,
    )

    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]

    # Verify comment unchanged
    await db_session.refresh(comment)
    assert comment.content == "Other's comment"


@pytest.mark.asyncio
async def test_get_comments_for_post(
    client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test getting comments for a post."""
    # Create a post
    post = models.Post(
        title="Post with Comments",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Create multiple comments
    comment1 = models.Comment(
        content="First comment",
        post_id=post.id,
        author_id=test_user.id,
    )
    comment2 = models.Comment(
        content="Second comment",
        post_id=post.id,
        author_id=test_user.id,
    )
    db_session.add_all([comment1, comment2])
    await db_session.commit()

    response = await client.get(f"/posts/{post.id}/comments")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    # Verify comment structure
    for comment in data:
        assert "id" in comment
        assert "content" in comment
        assert "author" in comment
        assert "author_id" in comment
        assert "created_at" in comment

    # Verify specific comments exist
    comment_contents = [c["content"] for c in data]
    assert "First comment" in comment_contents
    assert "Second comment" in comment_contents


@pytest.mark.asyncio
async def test_get_comments_for_nonexistent_post(
    authorized_client: AsyncClient,
) -> None:
    """Test getting comments for a non-existent post."""
    response = await authorized_client.get("/posts/99999/comments")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_comments_empty_post(
    client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test getting comments for a post with no comments."""
    # Create a post without comments
    post = models.Post(
        title="Empty Post",
        content="Content",
        published=True,
        owner_id=test_user.id,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    response = await client.get(f"/posts/{post.id}/comments")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0

