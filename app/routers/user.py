import os
from pathlib import Path
import uuid
from fastapi import APIRouter, HTTPException, Depends, UploadFile
from typing import Optional, List

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.testing.suite.test_reflection import users
from starlette.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_204_NO_CONTENT, HTTP_200_OK, \
    HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_403_FORBIDDEN
from sqlalchemy.orm import Session, joinedload, selectinload
from app import schemas, models, utils, oauth2
from app.database import get_db
from app.config import settings
from app.models import File

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.post("/create", status_code=HTTP_201_CREATED, response_model=schemas.UserOut)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    try:

        hashed_password = utils.hash(user.password)
        user.password = hashed_password

        new_user = models.User(**user.model_dump())
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")


@router.put("/update/{id}", response_model=schemas.UserOut)
def update_user(id: int, user_update: schemas.UserUpdate, db: Session = Depends(get_db),
                current_user: int = Depends(oauth2.get_current_user)):
    try:
        user_query = db.query(models.User).filter(models.User.id == id)
        user = user_query.first()

        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        update_data = user_update.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No fields to update")

        if "email" in update_data:
            existing_user = db.query(models.User).filter(
                models.User.email == update_data["email"], models.User.id != id
            ).first()
            if existing_user:
                raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Email already exists")

        user_query.update(update_data, synchronize_session=False)
        db.commit()
        db.refresh(user)
        return user

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update user: {str(e)}")


@router.put("/password/update/{id}", response_model=schemas.UserOut)
def update_user_password(id: int, password_update: schemas.UserPasswordUpdate, db: Session = Depends(get_db),
                         current_user: int = Depends(oauth2.get_current_user)):
    try:
        user = db.query(models.User).filter(models.User.id == id).first()
        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")

        if not utils.verify(password_update.current_password, user.password):
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid password")

        hashed_password = utils.hash(password_update.new_password)
        user.password = hashed_password

        db.commit()
        db.refresh(user)
        return user

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update user: {str(e)}")


@router.put("/avatar/update/{id}", response_model=schemas.UserOut)
def update_user_avatar(
        id: int,
        file: Optional[UploadFile] = File(None),
        db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)
):
    try:
        user = db.query(models.User).filter(models.User.id == id).first()
        if not user:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")
        # Create directory if it doesn't exist

        if file is None:
            if user.avatar:
                if os.path.exists(user.avatar.filepath) and user.avatar.filepath:
                    try:
                        os.remove(user.avatar.filepath)
                    except Exception:
                        pass
                db.delete(user.avatar)
                db.commit()
                db.refresh(user)
            return user

        os.makedirs(settings.AVATAR_DIR, exist_ok=True)

        # Generate unique filename
        file_extension = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(settings.AVATAR_DIR, unique_filename)

        # Save file
        with open(file_path, "wb") as buffer:
            content = file.file.read()
            buffer.write(content)

        # Update database
        if user.avatar:
            # Delete old file
            if os.path.exists(user.avatar.filepath) and user.avatar.filepath:
                try:
                    os.remove(user.avatar.filepath)
                except Exception:
                    pass
            user.avatar.filename = file.filename
            user.avatar.filepath = file_path
            user.avatar.filetype = file.content_type
        else:
            avatar_file = models.File(
                filename=file.filename,
                filepath=file_path,
                filetype=file.content_type,
                user_id=id,
                post_id=None
            )
            db.add(avatar_file)

        db.commit()
        db.refresh(user)
        return user

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Failed to update avatar: {str(e)}")


@router.delete("/delete/id/{id}", status_code=HTTP_204_NO_CONTENT)
def delete_user(id: int, db: Session = Depends(get_db), current_user: int = Depends(oauth2.get_current_user)):
    try:
        user_query = db.query(models.User).filter(models.User.id == id)
        user = user_query.first()
        if user is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"User with id: {id} not found")
        if current_user.id != user.id:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN,
                                detail="Not authorized to perform requested action")
        try:
            if user.avatar and user.avatar.filepath and os.path.exists(user.avatar.filepath):
                os.remove(user.avatar.filepath)
        except Exception:
            pass

        user_query.delete(synchronize_session=False)
        db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        db.rollback()
        error_massage = "Failed to delete user: %s" % str(e)
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=error_massage)


@router.get("/id/{id}", response_model=schemas.UserOut)
def get_user(id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(models.User).options(
            joinedload(models.User.avatar)
        ).filter(models.User.id == id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/all", response_model=List[schemas.UserOut])
def get_all_users(db: Session = Depends(get_db)):
    try:
        users = db.query(models.User).options(
            joinedload(models.User.avatar)
        ).all()
        return users
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR)
