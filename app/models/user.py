"""User model for LINE users."""

from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field


# Default OCR limit per session
DEFAULT_OCR_LIMIT = 20

# Daily free pages
DAILY_FREE_PAGES = 5


class User(Document):
    """User model for LINE users."""

    line_user_id: str = Field(..., unique=True, index=True)
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = Field(default=0)
    display_name: Optional[str] = None

    # OCR Usage Tracking
    ocr_count_session: int = Field(default=0, description="OCR pages used in current session (resettable by admin)")
    ocr_limit: int = Field(default=DEFAULT_OCR_LIMIT, description="Max OCR pages allowed per session (admin adjustable)")
    ocr_count_total: int = Field(default=0, description="Total OCR pages processed (all time)")

    # Daily free claim
    last_free_claim: Optional[datetime] = Field(default=None, description="Last time user claimed daily free pages")

    @property
    def ocr_remaining(self) -> int:
        """Get remaining OCR quota for this session."""
        return max(0, self.ocr_limit - self.ocr_count_session)

    @property
    def is_ocr_limit_reached(self) -> bool:
        """Check if user has reached their OCR limit."""
        return self.ocr_count_session >= self.ocr_limit

    @property
    def can_claim_free_today(self) -> bool:
        """Check if user can claim daily free pages (resets at midnight UTC+7)."""
        if self.last_free_claim is None:
            return True

        from datetime import timezone, timedelta
        # Thailand timezone (UTC+7)
        tz_th = timezone(timedelta(hours=7))
        now_th = datetime.now(tz_th)
        last_claim_th = self.last_free_claim.replace(tzinfo=timezone.utc).astimezone(tz_th)

        # Check if last claim was on a different day (Thailand time)
        return now_th.date() > last_claim_th.date()

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
                "ocr_count_session": 10,
                "ocr_limit": 50,
                "ocr_count_total": 150,
            }
        }
