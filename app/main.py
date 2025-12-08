from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import events
from app.redis_client import close_redis
from app.redis_client import init_redis
from app.routers import auth
from app.routers import comment
from app.routers import like
from app.routers import post
from app.routers import status
from app.routers import user


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    yield
    await close_redis()


app = FastAPI(lifespan=lifespan)
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user.router)
app.include_router(post.router)
app.include_router(auth.router)
app.include_router(like.router)
app.include_router(comment.router)
app.include_router(status.router)

# app.mount("/uploads/avatars", StaticFiles(directory="uploads/avatars"), name="avatars")
# app.mount("/uploads/post_files", StaticFiles(directory="uploads/post_files"), name="post_files")


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}
