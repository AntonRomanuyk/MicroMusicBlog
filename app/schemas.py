from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class PostBase(BaseModel):
    title: str
    content: str
    published: bool


class CreatePost(PostBase):
    pass


class UpdatePost(PostBase):
    pass


class UserBase(BaseModel):
    email: str
    password: str


class UserCreate(UserBase):
    pass


class UserLogin(UserBase):
    pass


class CommentBase(BaseModel):
    content: str


class CommentCreate(CommentBase):
    pass


class CommentUpdate(CommentBase):
    pass


class FileBase(BaseModel):
    filename: str
    filepath: str
    filetype: str


class FileOut(FileBase):
    id: int
    created_at: datetime
    updated_at: datetime
    post_id: int
    user_id: int

    class Config:
        orm_mode = True


class UserOut(BaseModel):
    id: int
    email: str
    nickname: str
    created_at: datetime
    updated_at: datetime
    avatar: Optional[FileOut] = None

    class Config:
        orm_mode = True


class CommentOut(CommentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    author_id: int
    author: UserOut

    class Config:
        orm_mode = True


class Post(PostBase):
    id: int
    created_at: datetime
    updated_at: datetime
    owner_id: int
    owner: UserOut
    comments: List[CommentOut] = []
    files: List[FileOut] = []
    liked_by: List[UserOut] = []
    likes: int

    class Config:
        orm_mode = True


class PostOut(BaseModel):
    Post: Post

    class Config:
        orm_mode = True
