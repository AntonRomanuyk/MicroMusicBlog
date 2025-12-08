import pytest
from httpx import AsyncClient
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.tests.conftest import create_test_user


@pytest.mark.asyncio
async def test_like_post_success(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test liking a post and verify the likes counter increments."""
    # Create another user and their post
    other_user = await create_test_user(
        db_session,
        #email="other@example.com",
        password="password123",
        #nickname="otheruser",
    )

    post = models.Post(
        title="Post to Like",
        content="Content",
        published=True,
        owner_id=other_user.id,
        likes=0,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    initial_likes = post.likes

    response = await authorized_client.post(f"/posts/{post.id}/like")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == post.id
    assert data["likes"] == initial_likes + 1

    # Verify DB state - likes counter incremented
    await db_session.refresh(post)
    assert post.likes == initial_likes + 1

    # Verify like relationship exists
    result = await db_session.execute(
        select(models.post_likes).where(
            models.post_likes.c.post_id == post.id,
            models.post_likes.c.user_id == test_user.id,
        )
    )
    like_record = result.scalar_one_or_none()
    assert like_record is not None


@pytest.mark.asyncio
async def test_like_post_twice_should_fail(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test that liking the same post twice should fail."""
    # Create another user and their post
    other_user = await create_test_user(
        db_session,
        #email="other2@example.com",
        password="password123",
        #nickname="otheruser2",
    )

    post = models.Post(
        title="Post to Like Twice",
        content="Content",
        published=True,
        owner_id=other_user.id,
        likes=0,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # First like - should succeed
    response1 = await authorized_client.post(f"/posts/{post.id}/like")
    assert response1.status_code == 200

    # Second like - should fail
    response2 = await authorized_client.post(f"/posts/{post.id}/like")
    assert response2.status_code == 403
    assert "already liked" in response2.json()["detail"].lower()

    # Verify likes counter only incremented once
    await db_session.refresh(post)
    assert post.likes == 1


@pytest.mark.asyncio
async def test_unlike_post_success(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test unliking a post and verify the likes counter decrements."""
    # Create another user and their post
    other_user = await create_test_user(
        db_session,
        #email="other3@example.com",
        password="password123",
        #nickname="otheruser3",
    )

    post = models.Post(
        title="Post to Unlike",
        content="Content",
        published=True,
        owner_id=other_user.id,
        likes=1,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Create existing like relationship
    await db_session.execute(
        insert(models.post_likes).values(user_id=test_user.id, post_id=post.id)
    )
    await db_session.commit()

    initial_likes = post.likes
    assert initial_likes == 1

    response = await authorized_client.delete(f"/posts/{post.id}/like")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == post.id
    assert data["likes"] == initial_likes - 1

    # Verify DB state - likes counter decremented
    await db_session.refresh(post)
    assert post.likes == initial_likes - 1

    # Verify like relationship removed
    result = await db_session.execute(
        select(models.post_likes).where(
            models.post_likes.c.post_id == post.id,
            models.post_likes.c.user_id == test_user.id,
        )
    )
    like_record = result.scalar_one_or_none()
    assert like_record is None


@pytest.mark.asyncio
async def test_unlike_post_not_liked_should_fail(
    authorized_client: AsyncClient,
    test_user: models.User,
    db_session: AsyncSession,
) -> None:
    """Test that unliking a post that wasn't liked should fail."""
    # Create another user and their post
    other_user = await create_test_user(
        db_session,
        #email="other4@example.com",
        password="password123",
        #nickname="otheruser4",
    )

    post = models.Post(
        title="Post Not Liked",
        content="Content",
        published=True,
        owner_id=other_user.id,
        likes=0,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    response = await authorized_client.delete(f"/posts/{post.id}/like")

    assert response.status_code == 403
    assert "not liked" in response.json()["detail"].lower()

    # Verify likes counter unchanged
    await db_session.refresh(post)
    assert post.likes == 0


@pytest.mark.asyncio
async def test_like_nonexistent_post(
    authorized_client: AsyncClient,
) -> None:
    """Test liking a non-existent post."""
    response = await authorized_client.post("/posts/99999/like")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unlike_nonexistent_post(
    authorized_client: AsyncClient,
) -> None:
    """Test unliking a non-existent post."""
    response = await authorized_client.delete("/posts/99999/like")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

