from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(100), default='')
    company: Mapped[str] = mapped_column(String(100), default='')
    bio: Mapped[str] = mapped_column(String(500), default='')
    wanted: Mapped[list] = mapped_column(JSON, default=list)
    offered: Mapped[list] = mapped_column(JSON, default=list)
    availability: Mapped[list] = mapped_column(JSON, default=list)
    visible: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    expires_at: Mapped[int] = mapped_column(Integer)

class Topic(Base):
    __tablename__ = 'topics'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

class Slot(Base):
    __tablename__ = 'slots'
    id: Mapped[int] = mapped_column(primary_key=True)
    starts_at: Mapped[int] = mapped_column(Integer)
    ends_at: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(150))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

class Invitation(Base):
    __tablename__ = 'invitations'
    id: Mapped[int] = mapped_column(primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    recipient_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    slot_id: Mapped[int] = mapped_column(ForeignKey('slots.id'))
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id'))
    message: Mapped[str] = mapped_column(String(300), default='')
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_at: Mapped[int] = mapped_column(Integer)
    accepted_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

class Booking(Base):
    __tablename__ = 'bookings'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey('slots.id'), primary_key=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey('invitations.id', ondelete='CASCADE'))

class Feedback(Base):
    __tablename__ = 'feedback'
    id: Mapped[int] = mapped_column(primary_key=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey('invitations.id', ondelete='CASCADE'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    happened: Mapped[bool] = mapped_column(Boolean)
    useful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    __table_args__ = (UniqueConstraint('invitation_id', 'user_id'),)
