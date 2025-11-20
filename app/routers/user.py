import os
from pathlib import Path
import uuid
import asyncio
from typing import Optional, List

import aiofiles
import aiofiles.os
import aiofiles.ospath as aiopath
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from sqlalchemy import func, and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_204_NO_CONTENT, HTTP_200_OK, \
    HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_403_FORBIDDEN
from sqlalchemy.orm import Session, joinedload, selectinload
from app import schemas, models, utils, oauth2, cache
from app.database import get_db
from app.config import settings

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.post("/create", status_code=HTTP_201_CREATED, response_model=schemas.UserOut)
async def create_user(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    try:

        hashed_password = await utils.hash(user.password)
        user.password = hashed_password

        new_user = models.User(**user.model_dump())
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")


@router.put("/update/{id}", response_model=schemas.UserOut)
async def update_user(id: int, user_update: schemas.UserUpdate, db: AsyncSession = Depends(get_db),
                current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        user = await db.get(models.User, id)

        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        update_data = user_update.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No fields to update")

        if "email" in update_data:
            query = select(models.User).filter(
                models.User.email == update_data["email"],
                models.User.id != id
            )
            result = await db.execute(query)
            existing_user = result.scalars().first()
            if existing_user:
                raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Email already exists")

        for key, value in update_data.items():
            setattr(user, key, value)

        await db.commit()
        await db.refresh(user)
        return user

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update user: {str(e)}")


@router.put("/password/update/{id}", response_model=schemas.UserOut)
async def update_user_password(id: int, password_update: schemas.UserPasswordUpdate, db: AsyncSession = Depends(get_db),
                         current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        user = await db.get(models.User, id)
        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        if not await utils.verify(password_update.current_password, user.password):
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid password")

        hashed_password = await utils.hash(password_update.new_password)
        user.password = hashed_password

        await db.commit()
        await db.refresh(user)
        return user

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update user: {str(e)}")


@router.put("/avatar/update/{id}", response_model=schemas.UserOut)
async def update_user_avatar(
        id: int,
        file: Optional[UploadFile] = File(None),
        db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    try:
        query = select(models.User).options(joinedload(models.User.avatar)).filter(models.User.id == id)
        result = await db.execute(query)
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        if file is None:
            if user.avatar:
                if user.avatar.filepath and await aiopath.exists(user.avatar.filepath):
                    try:
                        await aiofiles.os.remove(user.avatar.filepath)
                    except Exception:
                        pass
                await db.delete(user.avatar)
                await db.commit()
                await db.refresh(user)
            return user

        os.makedirs(settings.AVATAR_DIR, exist_ok=True)

        # Generate unique filename
        file_extension = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(settings.AVATAR_DIR, unique_filename)

        async with aiofiles.open(file_path, "wb") as buffer:
            content = await file.read()
            await buffer.write(content)

        if user.avatar:
            if user.avatar.filepath and await aiopath.exists(user.avatar.filepath):
                try:
                    await aiofiles.os.remove(user.avatar.filepath)
                except Exception:
                    pass
            user.avatar.filename = file.filename
            user.avatar.filepath = file_path
            user.avatar.filetype = file.content_type
        else:
            avatar_file = models.AvatarFile(
                filename=file.filename,
                filepath=file_path,
                filetype=file.content_type,
                user_id=id
            )
            db.add(avatar_file)

        await db.commit()
        await db.refresh(user)
        return user

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update avatar: {str(e)}")


@router.delete("/delete/id/{id}", status_code=HTTP_204_NO_CONTENT)
async def delete_user(id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)):
    try:
        query = select(models.User).options(joinedload(models.User.avatar)).filter(models.User.id == id)
        result = await db.execute(query)
        user = result.scalars().first()
        if user is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        try:
            if user.avatar and user.avatar.filepath and await aiopath.exists(user.avatar.filepath):
                await aiofiles.os.remove(user.avatar.filepath)
                await db.delete(user.avatar)
        except Exception:
            pass

        user.is_deleted = True
        user.deleted_at = func.now()
        user.nickname = "Deleted User"
        user.email = f"deleted_{user.id}@deleted.invalid"
        user.password = "<deleted>"
        await db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        await db.rollback()
        error_message = "Failed to delete user: %s" % str(e)
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=error_message)


@router.get("/id/{id}", response_model=schemas.UserOut)
async def get_user(id: int, db: AsyncSession = Depends(get_db)):
    try:
        cache_key = f"user:{id}"

        async def fetch_data_from_db():
            query = select(models.User).options(
                joinedload(models.User.avatar)
            ).filter(and_(models.User.id == id, models.User.is_deleted == False))

            result = await db.execute(query)
            user = result.scalars().first()

            if not user:
                return None
            user_schema = schemas.UserOut.model_validate(user, from_attributes=True)
            return user_schema.model_dump()

        data = await cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if not data:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")
        return data
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/all", response_model=List[schemas.UserOut])
async def get_all_users(db: AsyncSession = Depends(get_db)):
    try:
        cache_key = f"user:all"
        async def fetch_data_from_db():
            query = select(models.User).options(
                joinedload(models.User.avatar)
            ).filter(models.User.is_deleted == False)

            result = await db.execute(query)
            users = result.scalars().all()
            return [schemas.UserOut.model_validate(u, from_attributes=True).model_dump() for u in users]

        data = await cache.fetch_with_stampede_protection(key=cache_key,
                                                    fetch_func=fetch_data_from_db, expire=settings.cache_TTL)
        if not data:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Users not found")
        return data
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)
