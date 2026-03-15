from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from app.database import Base


class Link(Base):
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(50), unique=True, nullable=False, index=True)
    original_url = Column(String(2048), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    expired_at = Column(DateTime(timezone=True), nullable=True)
    is_expired = Column(Boolean, default=False, nullable=False)
    click_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    project_name = Column(String(100), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
