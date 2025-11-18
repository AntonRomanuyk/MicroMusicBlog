import os
import uuid
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_204_NO_CONTENT, HTTP_200_OK, \
    HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_403_FORBIDDEN
from typing import Optional, List
from fastapi import FastAPI, HTTPException, APIRouter, Depends, UploadFile, File, Query

from app import schemas, models, oauth2, cache
from app.config import settings
from app.database import get_db

from sqlalchemy.orm import Session, joinedload, selectinload

router = APIRouter(
    prefix="/posts",
    tags=['Posts']
)


@router.post("/create", status_code=HTTP_201_CREATED, response_model=schemas.Post)
def create_post(post: schemas.CreatePost, db: Session = Depends(get_db),
                current_user: schemas.UserOut = Depends(oauth2.get_current_user),
                files: Optional[List[UploadFile]] = File(None)):
    try:
        new_post = models.Post(owner_id = current_user.id, **post.model_dump())
        db.add(new_post)
        db.commit()
        db.refresh(new_post)

        if files:
            os.makedirs(settings.POST_FILES_DIR, exist_ok=True)

            for file in files:
                if file.filename:
                    file_extension = Path(file.filename).suffix
                    unique_filename = f"{uuid.uuid4()}{file_extension}"
                    file_path = os.path.join(settings.POST_FILES_DIR, unique_filename)

                    with open(file_path, "wb") as buffer:
                        content = file.file.read()
                        buffer.write(content)

                    post_file = models.PostFile(
                        filename = file.filename,
                        filepath=file_path,
                        filetype=file.content_type or "application/octet-stream",
                        post_id = new_post.id,
                    )
                    db.add(post_file)
            db.commit()
            db.refresh(new_post)
        return new_post
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")


@router.put("/update/id/{id}", status_code=HTTP_200_OK, response_model=schemas.Post)
def update_post(id: int, updated_post: schemas.UpdatePost, db: Session = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
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


@router.put("/update/id/{id}/files", status_code=HTTP_200_OK, response_model=schemas.Post)
def update_post_files(id: int, files: Optional[List[UploadFile]] = File(None),
                      db: Session = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        post_query = db.query(models.Post).filter(models.Post.id == id)
        post = post_query.first()
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        if current_user.id != post.owner_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        try:
            existing_files = db.query(models.PostFile).filter(models.PostFile.post_id == id).all()
            for post_file in existing_files:
                if post_file.filepath and os.path.exists(post_file.filepath):
                    os.remove(post_file.filepath)
                db.delete(post_file)
        except Exception:
            pass

        if files:
            os.makedirs(settings.POST_FILES_DIR, exist_ok=True)

            for file in files:
                if file.filename:
                    file_extension = Path(file.filename).suffix
                    unique_filename = f"{uuid.uuid4()}{file_extension}"
                    file_path = os.path.join(settings.POST_FILES_DIR, unique_filename)

                    with open(file_path, "wb") as buffer:
                        content = file.file.read()
                        buffer.write(content)

                    post_file = models.PostFile(
                        filename=file.filename,
                        filepath=file_path,
                        filetype=file.content_type or "application/octet-stream",
                        post_id=id
                    )
                    db.add(post_file)
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
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update post's files: {str(e)}")



@router.delete("/delete/id/{id}", status_code=HTTP_204_NO_CONTENT)
def delete_post(id: int, db: Session = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        post_query = db.query(models.Post).filter(models.Post.id == id)
        post = post_query.first()
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")
        if current_user.id != post.owner_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                            detail="Not authorized to perform requested action")

        try:
            post_files = db.query(models.PostFile).filter(models.PostFile.post_id == id).all()
            for post_file in post_files:
                if post_file.filepath and os.path.exists(post_file.filepath):
                    os.remove(post_file.filepath)
        except Exception:
            pass


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
        cache_key = f"post:{id}"

        def fetch_data_from_db():
            post = db.query(models.Post).options(
                joinedload(models.Post.owner),
                selectinload(models.Post.comments).joinedload(models.Comment.author),
                selectinload(models.Post.files),
                selectinload(models.Post.liked_by)
            ).filter(models.Post.id == id).first()

            if not post:
                return None
            post_schema = schemas.Post.model_validate(post, from_attributes=True)
            return post_schema.model_dump()

        data = cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if not data:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Post not found")

        return data
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/all", response_model=List[schemas.Post])
def get_all_posts(db: Session = Depends(get_db)):
    try:
        cache_key = f"posts:all"
        def fetch_data_from_db():
            posts = db.query(models.Post).options(
                joinedload(models.Post.owner),
                selectinload(models.Post.comments).joinedload(models.Comment.author),
                selectinload(models.Post.files),
                selectinload(models.Post.liked_by)
            ).all()
            return [schemas.Post.model_validate(u, from_attributes=True).model_dump() for u in posts]

        data = cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if data is None:
            return []

        return data
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/user/{id}/all", response_model=List[schemas.Post])
def get_all_user_posts(id: int, db: Session = Depends(get_db)):
    try:
        cache_key = f"posts:user:{id}:all"
        def fetch_data_from_db():
            posts = db.query(models.Post).options(
                joinedload(models.Post.owner),
                selectinload(models.Post.comments).joinedload(models.Comment.author),
                selectinload(models.Post.files),
                selectinload(models.Post.liked_by)
            ).filter(models.Post.owner_id == id).all()
            return [schemas.Post.model_validate(u, from_attributes=True).model_dump() for u in posts]

        data = cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if data is None:
            return []

        return data
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/user/{id}/likes", response_model=List[schemas.Post])
def get_all_user_likes(id: int, db: Session = Depends(get_db)):
    try:
        cache_key = f"posts:user:{id}:likes"
        def fetch_data_from_db():
            posts = db.query(models.Post).options(
                joinedload(models.Post.owner),
                selectinload(models.Post.comments).joinedload(models.Comment.author),
                selectinload(models.Post.files),
                selectinload(models.Post.liked_by)
            ).filter(models.Post.liked_by.any(models.User.id == id)).all()
            return [schemas.Post.model_validate(u, from_attributes=True).model_dump() for u in posts]

        data = cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if data is None:
            return []

        return data
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)