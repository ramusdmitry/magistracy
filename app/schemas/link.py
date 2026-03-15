from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl


class LinkShortenRequest(BaseModel):
    original_url: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None
    project_name: Optional[str] = None


class LinkCreate(BaseModel):
    original_url: str
    short_code: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None
    project_name: Optional[str] = None


class LinkUpdate(BaseModel):
    original_url: str


class LinkResponse(BaseModel):
    id: int
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    project_name: Optional[str] = None

    class Config:
        from_attributes = True


class LinkStats(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    click_count: int
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True
