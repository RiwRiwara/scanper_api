"""User model for LINE users."""

from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field


class User(Document):
    """User model for LINE users."""

    line_user_id: str = Field(..., unique=True, index=True)
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = Field(default=0)
    display_name: Optional[str] = None

    class Settings:
        name = "users"  # MongoDB collection name
        indexes = [
            "line_user_id",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "line_user_id": "U1234567890abcdef1234567890abcdef",
                "first_seen_at": "2026-01-03T10:00:00",
                "last_seen_at": "2026-01-03T10:05:00",
                "message_count": 5,
                "display_name": "John Doe",
            }
        }
