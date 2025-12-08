import os
import uuid
from pathlib import Path

import aiofiles
import aiofiles.os
import aiofiles.ospath as aiopath
from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import HTTPException
from fastapi import UploadFile
from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from starlette.status import HTTP_201_CREATED
from starlette.status import HTTP_204_NO_CONTENT
from starlette.status import HTTP_400_BAD_REQUEST
from starlette.status import HTTP_403_FORBIDDEN
from starlette.status import HTTP_404_NOT_FOUND
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app import cache
from app import models
from app import oauth2
from app import schemas
from app import utils
from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/create", status_code=HTTP_201_CREATED, response_model=schemas.UserOut)
async def create_user(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        existing = await db.execute(select(models.User.id).where(models.User.email == user.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Email already exists")

        hashed_password = await utils.hash(user.password)

        user_dict = user.model_dump()
        user_dict["password"] = hashed_password

        new_user = models.User(**user_dict)
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}") from e


@router.put("/update/{id}", response_model=schemas.UserOut)
async def update_user(
    id: int,
    user_update: schemas.UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.UserOut = Depends(oauth2.get_current_user),
):
    try:
        user = await db.get(models.User, id)

        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not authorized to perform requested action")

        update_data = user_update.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No fields to update")

        if "email" in update_data:
            query = select(models.User).filter(models.User.email == update_data["email"], models.User.id != id)
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
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}") from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update user: {str(e)}") from e


@router.put("/password/update/{id}", response_model=schemas.UserOut)
async def update_user_password(
    id: int,
    password_update: schemas.UserPasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.UserOut = Depends(oauth2.get_current_user),
):
    try:
        user = await db.get(models.User, id)
        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not authorized to perform requested action")

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
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}") from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update user: {str(e)}") from e


@router.put("/avatar/update/{id}", response_model=schemas.UserOut)
async def update_user_avatar(
    id: int,
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: schemas.UserOut = Depends(oauth2.get_current_user),
):
    try:
        query = select(models.User).options(joinedload(models.User.avatar)).filter(models.User.id == id)
        result = await db.execute(query)
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not authorized to perform requested action")

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
                filename=file.filename, filepath=file_path, filetype=file.content_type, user_id=id
            )
            db.add(avatar_file)

        await db.commit()
        await db.refresh(user)
        return user

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update avatar: {str(e)}") from e


@router.delete("/delete/id/{id}", status_code=HTTP_204_NO_CONTENT)
async def delete_user(
    id: int, db: AsyncSession = Depends(get_db), current_user: schemas.UserOut = Depends(oauth2.get_current_user)
):
    try:
        query = select(models.User).options(joinedload(models.User.avatar)).filter(models.User.id == id)
        result = await db.execute(query)
        user = result.scalars().first()
        if user is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Not authorized to perform requested action")

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
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {e}") from e
    except Exception as e:
        await db.rollback()
        error_message = f"Failed to delete user: {e}"
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=error_message) from e


@router.get("/id/{id}", response_model=schemas.UserOut)
async def get_user(id: int, db: AsyncSession = Depends(get_db)):
    try:
        cache_key = f"user:{id}"

        async def fetch_data_from_db():
            query = (
                select(models.User)
                .options(joinedload(models.User.avatar))
                .filter(and_(models.User.id == id, models.User.is_deleted.is_(False)))
            )

            result = await db.execute(query)
            user = result.scalars().first()

            if not user:
                return None
            user_schema = schemas.UserOut.model_validate(user, from_attributes=True)
            return user_schema.model_dump()

        data = await cache.fetch_with_stampede_protection(
            key=cache_key, fetch_func=fetch_data_from_db, expire=settings.cache_ttl
        )
        if not data:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR) from e


@router.get("/all", response_model=list[schemas.UserOut])
async def get_all_users(db: AsyncSession = Depends(get_db)):
    try:
        cache_key = "users:all"

        async def fetch_data_from_db():
            query = (
                select(models.User).options(joinedload(models.User.avatar)).filter(models.User.is_deleted.is_(False))
            )

            result = await db.execute(query)
            users = result.scalars().all()
            return [schemas.UserOut.model_validate(u, from_attributes=True).model_dump() for u in users]

        data = await cache.fetch_with_stampede_protection(
            key=cache_key, fetch_func=fetch_data_from_db, expire=settings.cache_ttl
        )
        if not data:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Users not found")
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR) from e
