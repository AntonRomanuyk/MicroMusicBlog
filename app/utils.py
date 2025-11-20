import asyncio

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def hash(password: str):
    return await asyncio.to_thread(pwd_context.hash, password)


async def verify(plain_password, hashed_password):
    return await asyncio.to_thread(pwd_context.verify, plain_password, hashed_password)