"""Message model for storing LINE message history."""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class MessageType(str, Enum):
    """Message type enumeration."""

    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"


class Message(Document):
    """Message model for storing LINE message history."""

    user: Link[User]  # Reference to User document
    message_type: MessageType
    content: str  # Text content or extracted OCR text
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    line_message_id: Optional[str] = None

    class Settings:
        name = "messages"
        indexes = [
            "user",
            "timestamp",
            "message_type",
            [("user", 1), ("timestamp", -1)],  # Compound index for user history queries
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "message_type": "text",
                "content": "สวัสดีครับ",
                "metadata": {"role": "user"},
                "timestamp": "2026-01-03T10:00:00",
                "line_message_id": "12345678901234",
            }
        }
