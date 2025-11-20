from fastapi import Depends, HTTPException, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from sqlalchemy.exc import SQLAlchemyError
from starlette.status import HTTP_200_OK, HTTP_404_NOT_FOUND, HTTP_403_FORBIDDEN, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_400_BAD_REQUEST
from app import models, oauth2, schemas
from app.database import get_db


router = APIRouter(
    prefix="/posts",
    tags=["likes"]
)

@router.post('/{id}/like', status_code=HTTP_200_OK, response_model=schemas.Post)
async def like_post(id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        post = await db.get(models.Post, id)

        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        stmt = select(models.post_likes).where(
            models.post_likes.c.post_id == id,
            models.post_likes.c.user_id == current_user.id
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="You have already liked this post")

        await db.execute(
            insert(models.post_likes).values(user_id=current_user.id, post_id=id)
        )
        post.likes = post.likes + 1
        await db.commit()
        await db.refresh(post)
        return post

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to like post: {str(e)}")


@router.delete('/{id}/like', status_code=HTTP_200_OK, response_model=schemas.Post)
async def unlike_post(id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        post = await db.get(models.Post, id)
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        stmt = select(models.post_likes).where(
            models.post_likes.c.post_id == id,
            models.post_likes.c.user_id == current_user.id
        )
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="You have not liked this post")

        await db.execute(
            delete(models.post_likes).where(models.post_likes.c.post_id == id,
                                                models.post_likes.c.user_id == current_user.id)
        )
        post.likes = post.likes - 1
        await db.commit()
        await db.refresh(post)
        return post

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to like post: {str(e)}")


