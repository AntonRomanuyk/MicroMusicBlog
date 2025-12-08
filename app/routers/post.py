import os
import uuid
from pathlib import Path

import aiofiles
import aiofiles.os
import aiofiles.ospath as aiopath
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_204_NO_CONTENT, HTTP_200_OK, \
    HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_403_FORBIDDEN
from typing import Optional, List
from fastapi import HTTPException, APIRouter, Depends, UploadFile, File, Form

from app import schemas, models, oauth2, cache
from app.config import settings
from app.database import get_db

from sqlalchemy.orm import joinedload, selectinload

router = APIRouter(
    prefix="/posts",
    tags=['Posts']
)


@router.post("/create", status_code=HTTP_201_CREATED, response_model=schemas.Post)
async def create_post(title: str = Form(...), content: str = Form(...), topic: Optional[str] = Form(None),
                      published: bool = Form(True), db: AsyncSession = Depends(get_db),
                      current_user: schemas.UserOut = Depends(oauth2.get_current_user),
                      files: Optional[List[UploadFile]] = File(None)):
    try:
        new_post = models.Post(
            owner_id=current_user.id,
            title=title,
            content=content,
            topic=topic,
            published=published,
        )
        db.add(new_post)
        await db.commit()
        await db.refresh(new_post)

        if files:
            os.makedirs(settings.POST_FILES_DIR, exist_ok=True)

            for file in files:
                if file.filename:
                    file_extension = Path(file.filename).suffix
                    unique_filename = f"{uuid.uuid4()}{file_extension}"
                    file_path = os.path.join(settings.POST_FILES_DIR, unique_filename)

                    async with aiofiles.open(file_path, "wb") as buffer:
                        content = await file.read()
                        await buffer.write(content)

                    post_file = models.PostFile(
                        filename = file.filename,
                        filepath=file_path,
                        filetype=file.content_type or "application/octet-stream",
                        post_id = new_post.id,
                    )
                    db.add(post_file)
            await db.commit()
            await db.refresh(new_post)
        return new_post
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")


@router.put("/update/id/{id}", status_code=HTTP_200_OK, response_model=schemas.Post)
async def update_post(id: int, updated_post: schemas.UpdatePost, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        post = await db.get(models.Post, id)
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        if current_user.id != post.owner_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        update_data = updated_post.model_dump()
        for key, value in update_data.items():
            setattr(post, key, value)
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
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update post: {str(e)}")


@router.put("/update/id/{id}/files", status_code=HTTP_200_OK, response_model=schemas.Post)
async def update_post_files(id: int, files: Optional[List[UploadFile]] = File(None),
                      db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        post = await db.get(models.Post, id)
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")

        if current_user.id != post.owner_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        try:
            result = await db.execute(select(models.PostFile).filter(models.PostFile.post_id == id))
            existing_files = result.scalars().all()
            for post_file in existing_files:
                if post_file.filepath and await aiopath.exists(post_file.filepath):
                    await aiofiles.os.remove(post_file.filepath)
                await db.delete(post_file)
        except Exception:
            pass

        if files:
            os.makedirs(settings.POST_FILES_DIR, exist_ok=True)

            for file in files:
                if file.filename:
                    file_extension = Path(file.filename).suffix
                    unique_filename = f"{uuid.uuid4()}{file_extension}"
                    file_path = os.path.join(settings.POST_FILES_DIR, unique_filename)

                    async with aiofiles.open(file_path, "wb") as buffer:
                        content = await file.read()
                        await buffer.write(content)

                    post_file = models.PostFile(
                        filename=file.filename,
                        filepath=file_path,
                        filetype=file.content_type or "application/octet-stream",
                        post_id=id
                    )
                    db.add(post_file)
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
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update post's files: {str(e)}")



@router.delete("/delete/id/{id}", status_code=HTTP_204_NO_CONTENT)
async def delete_post(id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        post = await db.get(models.Post, id)
        if post is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found")
        if current_user.id != post.owner_id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                            detail="Not authorized to perform requested action")

        try:
            result = await db.execute(select(models.PostFile).filter(models.PostFile.post_id == id))
            post_files = result.scalars().all()
            for post_file in post_files:
                if post_file.filepath and await aiopath.exists(post_file.filepath):
                    await aiofiles.os.remove(post_file.filepath)
        except Exception:
            pass

        await db.delete(post)
        await db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        await db.rollback()
        error_message = "Failed to delete post: %s" % str(e)
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=error_message)


@router.get("/id/{id}", response_model=schemas.Post)
async def get_post(id: int, db: AsyncSession = Depends(get_db)):
    try:
        cache_key = f"post:{id}"

        async def fetch_data_from_db():
            query = select(models.Post).options(
                joinedload(models.Post.owner),
                selectinload(models.Post.comments).joinedload(models.Comment.author),
                selectinload(models.Post.files),
                selectinload(models.Post.liked_by)
            ).filter(models.Post.id == id)

            result = await db.execute(query)
            post = result.scalars().first()

            if not post:
                return None
            post_schema = schemas.Post.model_validate(post, from_attributes=True)
            return post_schema.model_dump()

        data = await cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if not data:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Post not found")

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/all", response_model=List[schemas.Post])
async def get_all_posts(db: AsyncSession = Depends(get_db)):
    try:
        cache_key = f"posts:all"
        async def fetch_data_from_db():
            query = select(models.Post).options(
                joinedload(models.Post.owner),
                selectinload(models.Post.comments).joinedload(models.Comment.author),
                selectinload(models.Post.files),
                selectinload(models.Post.liked_by)
            )
            result = await db.execute(query)
            posts = result.scalars().all()
            return [schemas.Post.model_validate(u, from_attributes=True).model_dump() for u in posts]

        data = await cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if data is None:
            return []

        return data
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/user/{id}/all", response_model=List[schemas.Post])
async def get_all_user_posts(id: int, db: AsyncSession = Depends(get_db)):
    try:
        cache_key = f"posts:user:{id}:all"
        async def fetch_data_from_db():
            user_check = await db.execute(select(models.User.id).filter(models.User.id == id))
            if not user_check.scalar():
                return None

            query = select(models.Post).options(
                joinedload(models.Post.owner),
                selectinload(models.Post.comments).joinedload(models.Comment.author),
                selectinload(models.Post.files),
                selectinload(models.Post.liked_by)
            ).filter(models.Post.owner_id == id)

            result = await db.execute(query)
            posts = result.scalars().all()
            return [schemas.Post.model_validate(u, from_attributes=True).model_dump() for u in posts]

        data = await cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if data is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/user/{id}/likes", response_model=List[schemas.Post])
async def get_all_user_likes(id: int, db: AsyncSession = Depends(get_db)):
    try:
        cache_key = f"posts:user:{id}:likes"
        async def fetch_data_from_db():
            user_check = await db.execute(select(models.User.id).filter(models.User.id == id))
            if not user_check.scalar():
                return None

            query = select(models.Post).options(
                joinedload(models.Post.owner),
                selectinload(models.Post.comments).joinedload(models.Comment.author),
                selectinload(models.Post.files),
                selectinload(models.Post.liked_by)
            ).filter(models.Post.liked_by.any(models.User.id == id))

            result = await db.execute(query)
            posts = result.scalars().all()
            return [schemas.Post.model_validate(u, from_attributes=True).model_dump() for u in posts]

        data = await cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if data is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/topics", response_model=List[str])
async def get_unique_topics(db: AsyncSession = Depends(get_db)):
    cache_key = "topics:unique"

    async def fetch_data_from_db():
        query = select(models.Post.topic).distinct().where(models.Post.topic.is_not(None))
        result = await db.execute(query)
        return result.scalars().all()

    topics = await cache.fetch_with_stampede_protection(key=cache_key, fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
    if topics is None:
        return []

    return topics