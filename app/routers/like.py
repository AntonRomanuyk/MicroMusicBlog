from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy import insert
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_200_OK
from starlette.status import HTTP_403_FORBIDDEN
from starlette.status import HTTP_404_NOT_FOUND

from app import models
from app import oauth2
from app import schemas
from app.database import get_db
from app.redis_client import redis_client

router = APIRouter(prefix="/posts", tags=["likes"])


@router.post("/{id}/like", status_code=HTTP_200_OK, response_model=schemas.Post)
async def like_post(
    id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    post = await db.get(models.Post, id)

    if post is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

    stmt_check = select(models.post_likes).where(
        models.post_likes.c.post_id == id, models.post_likes.c.user_id == current_user.id
    )
    result = await db.execute(stmt_check)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="You have already liked this post")

    await db.execute(insert(models.post_likes).values(user_id=current_user.id, post_id=id))

    stmt_update = (
        update(models.Post).where(models.Post.id == id).values(likes=models.Post.likes + 1).returning(models.Post)
    )

    result_update = await db.execute(stmt_update)
    updated_post = result_update.scalar_one()
    await db.commit()
    if redis_client:
        await redis_client.delete(f"posts:user:{current_user.id}:likes")

    return updated_post


@router.delete("/{id}/like", status_code=HTTP_200_OK, response_model=schemas.Post)
async def unlike_post(
    id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    post = await db.get(models.Post, id)
    if post is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

    stmt_check = select(models.post_likes).where(
        models.post_likes.c.post_id == id, models.post_likes.c.user_id == current_user.id
    )
    result = await db.execute(stmt_check)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="You have not liked this post")

    await db.execute(
        delete(models.post_likes).where(
            models.post_likes.c.post_id == id, models.post_likes.c.user_id == current_user.id
        )
    )
    stmt_update = (
        update(models.Post).where(models.Post.id == id).values(likes=models.Post.likes - 1).returning(models.Post)
    )

    result_update = await db.execute(stmt_update)
    updated_post = result_update.scalar_one()
    await db.commit()
    if redis_client:
        await redis_client.delete(f"posts:user:{current_user.id}:likes")
    return updated_post
