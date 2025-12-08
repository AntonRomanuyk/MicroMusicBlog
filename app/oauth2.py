from datetime import datetime
from datetime import timedelta
from datetime import timezone

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_401_UNAUTHORIZED

from app import cache
from app import database
from app import models
from app import schemas
from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days


async def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


async def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def verify_access_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        token_type: str = payload.get("type")

        if user_id is None or token_type != "access":
            raise credentials_exception
        token_data = schemas.TokenData(id=str(user_id))
    except JWTError as e:
        raise credentials_exception from e

    return token_data


async def verify_refresh_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        token_type: str = payload.get("type")

        if user_id is None or token_type != "refresh":
            raise credentials_exception
        token_data = schemas.TokenData(id=str(user_id))
    except JWTError as e:
        raise credentials_exception from e

    return token_data


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(database.get_db)
) -> schemas.UserOut:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = await verify_access_token(token, credentials_exception)
        if token_data.id is None:
            raise credentials_exception
        user_id = token_data.id
    except Exception as e:
        raise credentials_exception from e

    cache_key = f"user:{user_id}"

    async def fetch_user_from_db():
        result = await db.execute(select(models.User).filter(models.User.id == int(user_id)))
        user_orm = result.scalar_one_or_none()
        if not user_orm:
            return None

        user_schema = schemas.UserOut.model_validate(user_orm, from_attributes=True)
        user_dict_to_cache = user_schema.model_dump()
        return user_dict_to_cache

    user_dict = await cache.fetch_with_stampede_protection(cache_key, fetch_user_from_db, expire=settings.cache_ttl)

    if user_dict is None:
        raise credentials_exception

    if user_dict.get("is_deleted"):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, detail="Account has been deleted", headers={"WWW-Authenticate": "Bearer"}
        )

    return schemas.UserOut.model_validate(user_dict)
