from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


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
    nickname: str


class UserLogin(UserBase):
    pass


class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    email: Optional[str] = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str


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
    type: str

    model_config = ConfigDict(from_attributes=True)


class AvatarFileOut(FileOut):
    user_id: int


class PostFileOut(FileOut):
    post_id: int


class UserOut(BaseModel):
    id: int
    email: str
    nickname: str
    created_at: datetime
    updated_at: datetime
    avatar: Optional[AvatarFileOut] = None

    model_config = ConfigDict(from_attributes=True)


class CommentOut(CommentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    author_id: int
    author: UserOut

    model_config = ConfigDict(from_attributes=True)


class Post(PostBase):
    id: int
    created_at: datetime
    updated_at: datetime
    owner_id: int
    owner: UserOut
    comments: Optional[List[CommentOut]] = None
    files: Optional[List[PostFileOut]] = None
    liked_by: Optional[List[UserOut]] = None
    likes: int

    model_config = ConfigDict(from_attributes=True)


class PostOut(BaseModel):
    Post: Post

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    id: Optional[str] = None
