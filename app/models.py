import datetime
from sqlalchemy import Integer, String, Column, DateTime, func, Boolean, ForeignKey, Table
from sqlalchemy.ext.declarative import declared_attr, declarative_base
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.database import Base

post_likes = Table(
    "post_likes",
    Base.metadata,
    Column("user_id", Integer,
           ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("post_id", Integer,
           ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
)


class TimeStampedMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False)

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False)


class Post(TimeStampedMixin, Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)
    published = Column(Boolean, nullable=False, server_default='True')

    owner_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    owner = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete")
    liked_by = relationship("User", secondary=post_likes, back_populates="liked_posts")
    likes = Column(Integer, nullable=False, server_default='0')
    files = relationship("File", back_populates="post", cascade="all, delete")


class User(TimeStampedMixin, Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, nullable=False)
    nickname = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)

    posts = relationship("Post", back_populates="owner", cascade="all, delete")
    comments = relationship("Comment", back_populates="author", cascade="all, delete")
    liked_posts = relationship("Post", secondary=post_likes, back_populates="liked_by")
    avatar = relationship("File", back_populates="user", uselist=False, cascade="all, delete")


class Comment(TimeStampedMixin, Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True, nullable=False)
    content = Column(String, nullable=False)

    post_id = Column(Integer, ForeignKey('posts.id', ondelete='CASCADE'), nullable=False)
    author_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    author = relationship("User", back_populates="comments")
    post = relationship("Post", back_populates="comments")


class File(TimeStampedMixin, Base):
    __tablename__ = 'files'
    id = Column(Integer, primary_key=True, nullable=False)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    filetype = Column(String, nullable=False)
    type = Column(String, nullable=False)

    __mapper_args__ = {'polymorphic_identity': 'file', 'polymorphic_on': type}


class AvatarFile(File):
    __tablename__ = 'avatars'

    id = Column(Integer, ForeignKey('files.id', ondelete='CASCADE'),primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    user = relationship("User", back_populates="avatar")

    __mapper_args__ = {'polymorphic_identity': 'avatar'}


class PostFile(File):
    __tablename__ = 'post_files'

    id = Column(Integer, ForeignKey('files.id', ondelete='CASCADE'), primary_key=True, nullable=False)
    post_id = Column(Integer, ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    post = relationship("Post", back_populates="post_file")

    __mapper_args__ = {'polymorphic_identity': 'post_file'}
