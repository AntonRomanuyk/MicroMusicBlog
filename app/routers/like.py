from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy import insert
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_200_OK
from starlette.status import HTTP_400_BAD_REQUEST
from starlette.status import HTTP_403_FORBIDDEN
from starlette.status import HTTP_404_NOT_FOUND
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app import models
from app import oauth2
from app import schemas
from app.database import get_db

router = APIRouter(prefix="/posts", tags=["likes"])


@router.post("/{id}/like", status_code=HTTP_200_OK, response_model=schemas.Post)
async def like_post(
    id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    try:
        post = await db.get(models.Post, id)

        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        stmt = select(models.post_likes).where(
            models.post_likes.c.post_id == id, models.post_likes.c.user_id == current_user.id
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="You have already liked this post")

        await db.execute(insert(models.post_likes).values(user_id=current_user.id, post_id=id))
        post.likes = post.likes + 1
        await db.commit()
        await db.refresh(post)
        return post

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}") from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to like post: {str(e)}") from e


@router.delete("/{id}/like", status_code=HTTP_200_OK, response_model=schemas.Post)
async def unlike_post(
    id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    try:
        post = await db.get(models.Post, id)
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        stmt = select(models.post_likes).where(
            models.post_likes.c.post_id == id, models.post_likes.c.user_id == current_user.id
        )
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="You have not liked this post")

        await db.execute(
            delete(models.post_likes).where(
                models.post_likes.c.post_id == id, models.post_likes.c.user_id == current_user.id
            )
        )
        post.likes = post.likes - 1
        await db.commit()
        await db.refresh(post)
        return post

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}") from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to like post: {str(e)}") from e
