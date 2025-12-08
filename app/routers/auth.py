from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import database, schemas, models, utils, oauth2

router = APIRouter(tags=["Authentication"])

@router.post("/login", response_model=schemas.TokenResponse)
async def login(user_credentials: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(database.get_db)):

    user_query = await db.execute(select(models.User).filter(models.User.email == user_credentials.username))
    user = user_query.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect email or password")

    if not await utils.verify(user_credentials.password, user.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect email or password")


    access_token = await oauth2.create_access_token(data={"user_id": user.id})
    refresh_token = await oauth2.create_refresh_token(data={"user_id": user.id})
    
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.post("/refresh", response_model=schemas.Token)
async def refresh(refresh_token_request: schemas.RefreshTokenRequest, db: AsyncSession = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"}
    )
    
    try:
        token_data = await oauth2.verify_refresh_token(refresh_token_request.refresh_token, credentials_exception)
        user_result = await db.execute(select(models.User).filter(models.User.id == int(token_data.id)))
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise credentials_exception

        new_access_token = await oauth2.create_access_token(data={"user_id": user.id})
        
        return {
            "access_token": new_access_token,
            "token_type": "bearer"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
