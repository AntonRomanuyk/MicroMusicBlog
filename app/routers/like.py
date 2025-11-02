from fastapi import Depends, HTTPException, APIRouter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import select, insert, delete
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_204_NO_CONTENT, HTTP_200_OK, \
    HTTP_404_NOT_FOUND, HTTP_403_FORBIDDEN, HTTP_500_INTERNAL_SERVER_ERROR
from app import models, oauth2, schemas
from app.main import app
from app.database import get_db


router = APIRouter(
    prefix="/posts",
    tags=["likes"]
)

@router.post('/{id}/like', status_code=HTTP_200_OK, response_model=schemas.Post)
def like_post(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    try:
        post = db.get(models.Post, id)
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        stmt = select(models.post_likes).where(id == models.post_likes.c.post_id,
                                               current_user.id == models.post_likes.c.user_id)
        if db.execute(stmt).first():
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="You have already liked this post")

        db.execute(
            insert(models.post_likes).values(user_id=current_user.id, post_id=id)
        )
        post.likes += 1
        db.commit()
        db.refresh(post)
        return post

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to like post: {str(e)}")


@router.delete('/{id}/like', status_code=HTTP_200_OK, response_model=schemas.Post)
def unlike_post(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(oauth2.get_current_user)):
    try:
        post = db.get(models.Post, id)
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        stmt = select(models.post_likes).where(id == models.post_likes.c.post_id,
                                               current_user.id == models.post_likes.c.user_id)
        if not db.execute(stmt).first():
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="You have not liked this post")

        db.execute(
            delete(models.post_likes).where(id == models.post_likes.c.post_id,
                                               current_user.id == models.post_likes.c.user_id)
        )
        post.likes -= 1
        db.commit()
        db.refresh(post)
        return post

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to like post: {str(e)}")


