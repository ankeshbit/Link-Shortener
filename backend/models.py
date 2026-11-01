from database import Base
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(
        String(255), nullable=True
    )  # Nullable to allow passwordless OAuth registration
    google_id = Column(String(255), unique=True, index=True, nullable=True)
    firebase_uid = Column(String(128), unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Cascade deletes: If a user account is deleted, remove their links too
    urls = relationship("URL", back_populates="user", cascade="all, delete-orphan")


class URL(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True, index=True)
    short_id = Column(String(50), unique=True, index=True, nullable=False)
    target_url = Column(String, nullable=False)
    clicks_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    password = Column(String, nullable=True)

    # Optional association with User (guest shorteners will have user_id=None)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    user = relationship("User", back_populates="urls")
    clicks = relationship(
        "ClickEvent", back_populates="url", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_urls_user_id_created_at", "user_id", "created_at"),)


class ClickEvent(Base):
    __tablename__ = "click_events"

    id = Column(Integer, primary_key=True, index=True)
    url_id = Column(Integer, ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    ip_address = Column(String(50))
    country = Column(String(50))
    city = Column(String(50))
    lat = Column(Float)
    lon = Column(Float)
    user_agent = Column(String)
    browser = Column(String(50))
    os = Column(String(50))
    device = Column(String(50))
    clicked_at = Column(DateTime(timezone=True), server_default=func.now())

    url = relationship("URL", back_populates="clicks")
