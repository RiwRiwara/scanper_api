"""Payment model for tracking Beam payments."""

from datetime import datetime
from typing import Optional
from enum import Enum
from beanie import Document, Link
from pydantic import Field

from app.models.user import User


class PaymentStatus(str, Enum):
    """Payment status enum."""
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Payment(Document):
    """Payment model for tracking purchases."""

    # Beam charge info
    charge_id: str = Field(..., unique=True, index=True)
    reference_id: str = Field(..., index=True)

    # User info
    line_user_id: str = Field(..., index=True)

    # Payment details
    amount_satang: int = Field(..., description="Amount in satang (THB smallest unit)")
    pages_purchased: int = Field(..., description="Number of OCR pages purchased")
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # Payment method info (from webhook)
    payment_method_type: Optional[str] = None
    card_last4: Optional[str] = None
    card_brand: Optional[str] = None

    class Settings:
        name = "payments"
        indexes = [
            "charge_id",
            "reference_id",
            "line_user_id",
            "status",
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "charge_id": "ch_34duZsgqHJzkZZhMOl9wVcYzjRx",
                "reference_id": "scanper_pay_123456",
                "line_user_id": "U1234567890abcdef",
                "amount_satang": 1000,
                "pages_purchased": 20,
                "status": "SUCCEEDED",
                "created_at": "2026-01-03T10:00:00",
                "payment_method_type": "CARD",
                "card_last4": "1234",
                "card_brand": "VISA",
            }
        }


# Pricing constants
PRICE_PER_PAGE_SATANG = 50  # 0.50 THB per page
MIN_AMOUNT_SATANG = 1000  # 10 THB minimum
PAGES_PER_10_BAHT = 20  # 10 THB = 20 pages


def calculate_pages_from_amount(amount_satang: int) -> int:
    """Calculate number of pages from payment amount."""
    return (amount_satang // MIN_AMOUNT_SATANG) * PAGES_PER_10_BAHT


def calculate_amount_from_pages(pages: int) -> int:
    """Calculate amount in satang from number of pages."""
    packages = (pages + PAGES_PER_10_BAHT - 1) // PAGES_PER_10_BAHT
    return packages * MIN_AMOUNT_SATANG
