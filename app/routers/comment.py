from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload, joinedload
from starlette.status import HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_400_BAD_REQUEST, \
    HTTP_204_NO_CONTENT, HTTP_201_CREATED, HTTP_403_FORBIDDEN, HTTP_200_OK

from app import schemas, models, oauth2, cache
from app.database import get_db
from app.config import settings

router = APIRouter(
    prefix="/posts",
    tags=["comments"]
)


@router.post("/{id}/comment", response_model=schemas.CommentOut, status_code=HTTP_201_CREATED)
async def comment_post(id: int, comment: schemas.CommentCreate, db: AsyncSession = Depends(get_db),
                 current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        post_query = await db.execute(select(models.Post).filter(models.Post.id == id))
        post = post_query.scalar_one_or_none()

        if not post:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        new_comment = models.Comment(content=comment.content,
                                     post_id=id, author_id=current_user.id)
        db.add(new_comment)
        await db.commit()
        await db.refresh(new_comment)

        return new_comment

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to comment post: {str(e)}")


@router.delete("/comment/{id}", status_code=HTTP_204_NO_CONTENT)
async def delete_comment_on_post(id: int, db: AsyncSession = Depends(get_db),
                           current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        comment_query = await db.execute(select(models.Comment).filter(models.Comment.id == id))
        comment = comment_query.scalar_one_or_none()

        if not comment:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Comment with id: {id} not found")

        if current_user.id != comment.author_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        await db.execute(delete(models.Comment).filter(models.Comment.id == id))
        await db.commit()


    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to comment post: {str(e)}")


@router.put("/comment/{id}", response_model=schemas.CommentOut, status_code=HTTP_200_OK)
async def update_comment_on_post(id: int, new_comment: schemas.CommentUpdate, db: AsyncSession = Depends(get_db),
                           current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        comment_query = await db.execute(select(models.Comment).filter(models.Comment.id == id))
        comment = comment_query.scalar_one_or_none()

        if not comment:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Comment with id: {id} not found")
        
        if current_user.id != comment.author_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        await db.execute(
            update(models.Comment)
            .filter(models.Comment.id == id)
            .values(**new_comment.model_dump())
        )
        await db.commit()
        await db.refresh(comment)

        return comment
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update comment on post: {str(e)}")


@router.get("/{id}/comments", response_model=List[schemas.CommentOut], status_code=HTTP_200_OK)
async def get_comments_for_post(id: int, db: AsyncSession = Depends(get_db)):
    try:
        cache_key = f"comments:post:{id}"

        async def fetch_data_from_db():
            post_check = await db.execute(select(models.Post.id).filter(models.Post.id == id))
            if not post_check.scalar():
                return None

            result = await db.execute(
                select(models.Comment)
                .options(joinedload(models.Comment.author))
                .filter(models.Comment.post_id == id)
            )
            comments = result.scalars().all()

            serialized = [schemas.CommentOut.model_validate(c, from_attributes=True).model_dump() for c in comments]
            return serialized

        data = await cache.fetch_with_stampede_protection(key=cache_key,
            fetch_func=fetch_data_from_db,
            expire=settings.cache_TTL)
        if data is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)
