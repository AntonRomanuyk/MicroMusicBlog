from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone

from starlette.status import HTTP_401_UNAUTHORIZED

from app import schemas, database, models, cache
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='login')

SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc)+timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_access_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id: str = payload.get("user_id")
        token_type: str = payload.get("type")

        if id is None or token_type != "access":
            raise credentials_exception
        token_data = schemas.TokenData(id=id)
    except JWTError:
        raise credentials_exception

    return token_data


def verify_refresh_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id: str = payload.get("user_id")
        token_type: str = payload.get("type")

        if id is None or token_type != "refresh":
            raise credentials_exception
        token_data = schemas.TokenData(id=id)
    except JWTError:
        raise credentials_exception

    return token_data


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)) -> schemas.UserOut:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = verify_access_token(token, credentials_exception)
        if token_data.id is None:
            raise credentials_exception
        user_id = token_data.id
    except Exception:
        raise credentials_exception

    cache_key = f"user:{user_id}"

    def fetch_user_from_db():
        user_orm = db.query(models.User).filter(models.User.id == user_id).first()

        if not user_orm:
            return None

        user_schema = schemas.UserOut.model_validate(user_orm, from_attributes=True)
        user_dict_to_cache = user_schema.model_dump()
        return user_dict_to_cache

    user_dict = cache.fetch_with_stampede_protection(cache_key, fetch_user_from_db, expire=settings.cache_TTL)

    if user_dict is None:
        raise credentials_exception

    if user_dict.get("is_deleted"):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Account has been deleted",
            headers={"WWW-Authenticate": "Bearer"})

    return schemas.UserOut.model_validate(user_dict)