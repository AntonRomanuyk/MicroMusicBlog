from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from starlette.status import HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_400_BAD_REQUEST, \
    HTTP_204_NO_CONTENT, HTTP_201_CREATED, HTTP_403_FORBIDDEN, HTTP_200_OK

from app import schemas, models, oauth2
from app.database import get_db

router = APIRouter(
    prefix="/posts",
    tags=["comments"]
)


@router.post("/{id}/comment", response_model=schemas.CommentOut, status_code=HTTP_201_CREATED)
def comment_post(id: int, comment: schemas.CommentCreate, db: Session = Depends(get_db),
                 current_user: models.User = Depends(oauth2.get_current_user)):
    try:
        post_query = db.query(models.Post).filter(models.Post.id == id)
        post = post_query.first()

        if not post:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        new_comment = models.Comment(content=comment.content,
                                     post_id=id, author_id=current_user.id)
        db.add(new_comment)

        db.commit()
        db.refresh(new_comment)

        return new_comment
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to comment post: {str(e)}")


@router.delete("/comment/id/{id}", status_code=HTTP_204_NO_CONTENT)
def delete_comment_on_post(id: int, db: Session = Depends(get_db),
                           current_user: models.User = Depends(oauth2.get_current_user)):
    try:
        comment_query = db.query(models.Comment).filter(models.Comment.id == id)
        comment = comment_query.first()

        if not comment:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Comment with id: {id} not found")

        if current_user.id != comment.author_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        comment_query.delete(synchronize_session=False)
        db.commit()



    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to comment post: {str(e)}")


@router.put("/{id}/comment", response_model=schemas.CommentOut, status_code=HTTP_200_OK)
def update_comment_on_post(id: int, new_comment: schemas.CommentUpdate, db: Session = Depends(get_db),
                           current_user: models.User = Depends(oauth2.get_current_user)):
    try:
        comment_query = db.query(models.Comment).filter(models.Comment.id == id)
        comment = comment_query.first()

        if current_user.id != comment.author_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")
        if not comment:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Comment with id: {id} not found")

        comment_query.update(new_comment.model_dump(), synchronize_session=False)

        db.commit()
        db.refresh(comment)

        return comment
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update comment on post: {str(e)}")


@router.get("/{id}/comments", response_model=List[schemas.CommentOut], status_code=HTTP_200_OK)
def get_comments_for_post(id: int, db: Session = Depends(get_db)):
    try:
        comments_query = db.query(models.Comment).filter(models.Comment.post_id == id)
        comments = comments_query.options(
            joinedload(models.Comment.author)
        ).all()
        return comments
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)
