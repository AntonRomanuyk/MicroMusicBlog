import datetime

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.cache import CacheInvalidationMixin
from app.database import Base

post_likes = Table(
    "post_likes",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("post_id", Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
)


class TimeStampedMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Post(TimeStampedMixin, CacheInvalidationMixin, Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)
    topic = Column(String, nullable=True, index=True)
    published = Column(Boolean, nullable=False, server_default="True")

    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = relationship("User", back_populates="posts", lazy="selectin")
    comments = relationship("Comment", back_populates="post", cascade="all, delete", lazy="selectin")
    liked_by = relationship("User", secondary=post_likes, back_populates="liked_posts", lazy="selectin")
    likes = Column(Integer, nullable=False, server_default="0")
    files = relationship("PostFile", back_populates="post", cascade="all, delete", lazy="selectin")

    def get_cache_keys_to_invalidate(self) -> list[str]:
        return [
            f"post:{self.id}",
            "posts:all",
            f"posts:user:{self.owner_id}:all",
            f"posts:user:{self.owner_id}:likes",
            "topics:unique",
        ]


class User(TimeStampedMixin, CacheInvalidationMixin, Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, nullable=False)
    nickname = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)

    last_seen = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, nullable=False, server_default="False", index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    posts = relationship("Post", back_populates="owner")
    comments = relationship("Comment", back_populates="author")
    liked_posts = relationship("Post", secondary=post_likes, back_populates="liked_by")
    avatar = relationship("AvatarFile", back_populates="user", uselist=False, cascade="all, delete", lazy="selectin")

    def get_cache_keys_to_invalidate(self) -> list[str]:
        return [
            f"user:{self.id}",
            "users:all",
            f"posts:user:{self.id}:all",
            f"posts:user:{self.id}:likes",
        ]


class Comment(TimeStampedMixin, CacheInvalidationMixin, Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, nullable=False)
    content = Column(String, nullable=False)

    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    author = relationship("User", back_populates="comments", lazy="selectin")
    post = relationship("Post", back_populates="comments")

    def get_cache_keys_to_invalidate(self) -> list[str]:
        return [
            f"post:{self.post_id}",
            "posts:all",
            f"comments:post:{self.post_id}",
        ]


class File(TimeStampedMixin, CacheInvalidationMixin, Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, nullable=False)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    filetype = Column(String, nullable=False)
    type = Column(String, nullable=False)

    __mapper_args__ = {"polymorphic_identity": "file", "polymorphic_on": type}


class AvatarFile(File):
    __tablename__ = "avatars"

    id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    user = relationship("User", back_populates="avatar")

    __mapper_args__ = {"polymorphic_identity": "avatar"}

    def get_cache_keys_to_invalidate(self) -> list[str]:
        return [
            f"user:{self.user_id}",
            "users:all",
        ]


class PostFile(File):
    __tablename__ = "post_files"

    id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    post = relationship("Post", back_populates="files")

    __mapper_args__ = {"polymorphic_identity": "post_file"}

    def get_cache_keys_to_invalidate(self) -> list[str]:
        return [
            f"post:{self.post_id}",
            "posts:all",
        ]
