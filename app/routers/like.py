from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy import insert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_200_OK
from starlette.status import HTTP_403_FORBIDDEN
from starlette.status import HTTP_404_NOT_FOUND

from app import models
from app import oauth2
from app import schemas
from app.database import get_db

router = APIRouter(prefix="/posts", tags=["likes"])


@router.post("/{id}/like", status_code=HTTP_200_OK, response_model=schemas.Post)
async def like_post(
    id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    result = await db.execute(select(models.Post).where(models.Post.id == id).with_for_update())
    post = result.scalar_one_or_none()

    if post is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

    stmt_check = select(models.post_likes).where(
        models.post_likes.c.post_id == id, models.post_likes.c.user_id == current_user.id
    )
    if (await db.execute(stmt_check)).scalar_one_or_none():
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="You have already liked this post")

    await db.execute(insert(models.post_likes).values(user_id=current_user.id, post_id=id))

    post.likes += 1
    await db.commit()
    await db.refresh(post)

    return post


@router.delete("/{id}/like", status_code=HTTP_200_OK, response_model=schemas.Post)
async def unlike_post(
    id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    result = await db.execute(select(models.Post).where(models.Post.id == id).with_for_update())
    post = result.scalar_one_or_none()

    if post is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

    stmt_check = select(models.post_likes).where(
        models.post_likes.c.post_id == id, models.post_likes.c.user_id == current_user.id
    )
    if not (await db.execute(stmt_check)).scalar_one_or_none():
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="You have not liked this post")

    await db.execute(
        delete(models.post_likes).where(
            models.post_likes.c.post_id == id, models.post_likes.c.user_id == current_user.id
        )
    )

    post.likes -= 1
    await db.commit()
    await db.refresh(post)

    return post
