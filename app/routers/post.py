from sqlalchemy.exc import SQLAlchemyError
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_204_NO_CONTENT, HTTP_200_OK, \
    HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_403_FORBIDDEN
from typing import Optional, List
from fastapi import FastAPI, HTTPException, APIRouter, Depends

from app import schemas, models
from app.database import get_db

from sqlalchemy.orm import Session, joinedload, selectinload

router = APIRouter(
    prefix="/posts",
    tags=['Posts']
)


@router.post("/create", status_code=HTTP_201_CREATED, response_model=schemas.Post)
def create_post(post: schemas.CreatePost, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
    try:
        new_post = models.Post(owner_id = current_user.id, **post.model_dump())
        db.add(new_post)
        db.commit()
        db.refresh(new_post)
        return new_post
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")


@router.put("/update/id/{id}", status_code=HTTP_200_OK, response_model=schemas.Post)
def update_post(id: int, updated_post: schemas.UpdatePost, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
    try:
        post_query = db.query(models.Post).filter(models.Post.id == id)
        post = post_query.first()
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        if current_user.id != post.owner_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        post_query.update(updated_post.model_dump(), synchronize_session=False)
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
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update post: {str(e)}")


@router.delete("/delete/id/{id}", status_code=HTTP_204_NO_CONTENT)
def delete_post(id: int, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
    try:
        post_query = db.query(models.Post).filter(models.Post.id == id)
        post = post_query.first()
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")
        if current_user.id != post.owner_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                            detail="Not authorized to perform requested action")
        post_query.delete(synchronize_session=False)
        db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        error_massage = "Failed to delete post: %s" % str(e)
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=error_massage)


@router.get("/id/{id}", response_model=schemas.Post)
def get_post(id: int, db: Session = Depends(get_db)):
    try:
        post = db.query(models.Post).options(
            joinedload(models.Post.owner),
            selectinload(models.Post.comments).joinedload(models.Comment.author),
            selectinload(models.Post.files),
            selectinload(models.Post.liked_by)
        ).filter(models.Post.id == id).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        return post
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/all", response_model=List[schemas.Post])
def get_all_posts(db: Session = Depends(get_db)):
    try:
        posts = db.query(models.Post).options(
            joinedload(models.Post.owner),
            selectinload(models.Post.comments).joinedload(models.Comment.author),
            selectinload(models.Post.files),
            selectinload(models.Post.liked_by)
        ).all()
        return posts
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)
