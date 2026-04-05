from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class URL(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True, index=True)
    short_id = Column(String(10), unique=True, index=True, nullable=False)
    target_url = Column(String, nullable=False)
    clicks_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    clicks = relationship("ClickEvent", back_populates="url", cascade="all, delete-orphan")

class ClickEvent(Base):
    __tablename__ = "click_events"

    id = Column(Integer, primary_key=True, index=True)
    url_id = Column(Integer, ForeignKey("urls.id"))
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
