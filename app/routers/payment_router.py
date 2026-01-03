"""Payment Router for Beam payment integration."""

import logging
import hmac
import hashlib
import base64
import uuid
import httpx
from datetime import datetime
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional, List

from app.config import settings
from app.repositories.user_repository import user_repository
from app.models.payment import (
    Payment,
    PaymentStatus,
    MIN_AMOUNT_SATANG,
    PAGES_PER_10_BAHT,
    calculate_pages_from_amount,
)
from app.routers.liff_router import verify_line_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payment", tags=["Payment"])


# ============ Request/Response Models ============

class CreateChargeRequest(BaseModel):
    """Request to create a payment charge."""
    amount_thb: int  # Amount in THB (minimum 10)


class CreateChargeResponse(BaseModel):
    """Response from creating a charge."""
    charge_id: str
    reference_id: str
    amount_satang: int
    pages_to_receive: int
    action_required: str  # NONE, REDIRECT, ENCODED_IMAGE
    redirect_url: Optional[str] = None
    qr_code: Optional[str] = None  # Base64 QR code image for PromptPay


class PaymentPackage(BaseModel):
    """A payment package option."""
    amount_thb: int
    amount_satang: int
    pages: int
    label: str


class PaymentHistoryItem(BaseModel):
    """Payment history item."""
    charge_id: str
    amount_thb: float
    pages_purchased: int
    status: str
    created_at: str
    payment_method: Optional[str] = None


# ============ Helper Functions ============

def get_payment_packages() -> List[PaymentPackage]:
    """Get available payment packages."""
    packages = [
        {"amount_thb": 10, "pages": 20, "label": "20 pages"},
        {"amount_thb": 50, "pages": 100, "label": "100 pages"},
        {"amount_thb": 100, "pages": 200, "label": "200 pages"},
        {"amount_thb": 500, "pages": 1000, "label": "1,000 pages"},
    ]
    return [
        PaymentPackage(
            amount_thb=p["amount_thb"],
            amount_satang=p["amount_thb"] * 100,
            pages=p["pages"],
            label=p["label"],
        )
        for p in packages
    ]


def verify_beam_signature(payload: bytes, signature: str) -> bool:
    """Verify Beam webhook signature."""
    if not settings.BEAM_WEBHOOK_SECRET:
        logger.warning("BEAM_WEBHOOK_SECRET not configured, skipping verification")
        return True

    try:
        # Decode the base64 HMAC key
        key = base64.b64decode(settings.BEAM_WEBHOOK_SECRET)
        # Calculate HMAC-SHA256
        calculated = hmac.new(key, payload, hashlib.sha256).digest()
        # Encode as base64 and compare
        calculated_b64 = base64.b64encode(calculated).decode()
        return hmac.compare_digest(calculated_b64, signature)
    except Exception as e:
        logger.error(f"Error verifying Beam signature: {e}")
        return False


async def create_beam_charge(
    amount_satang: int,
    reference_id: str,
) -> dict:
    """Create a PromptPay charge via Beam API.

    Args:
        amount_satang: Amount in satang (1 THB = 100 satang)
        reference_id: Unique reference ID for this charge

    Returns:
        Beam API response with chargeId and QR code
    """
    auth_string = f"{settings.BEAM_MERCHANT_ID}:{settings.BEAM_API_KEY}"
    auth_b64 = base64.b64encode(auth_string.encode()).decode()

    payload = {
        "amount": amount_satang,
        "currency": "THB",
        "referenceId": reference_id,
        "paymentMethod": {
            "paymentMethodType": "QR_PROMPTPAY"
        },
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.BEAM_API_URL}/api/v1/charges",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth_b64}",
            },
            timeout=30.0,
        )

        response_data = response.json()
        logger.info(f"Beam API response: {response.status_code} - {response_data}")

        if response.status_code not in [200, 201]:
            logger.error(f"Beam API error: {response.status_code} - {response.text}")
            raise HTTPException(
                status_code=502,
                detail=f"Payment gateway error: {response.status_code}"
            )

        return response_data


# ============ API Endpoints ============

@router.get("/packages", response_model=List[PaymentPackage])
async def get_packages():
    """Get available payment packages."""
    return get_payment_packages()


@router.post("/create-charge", response_model=CreateChargeResponse)
async def create_charge(
    request: CreateChargeRequest,
    authorization: str = Header(..., description="Bearer <LINE_ACCESS_TOKEN>"),
):
    """
    Create a payment charge for purchasing OCR pages.

    Minimum: 10 THB = 20 pages
    """
    # Verify LINE token
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    access_token = authorization[7:]
    profile = await verify_line_access_token(access_token)
    line_user_id = profile.get("userId")

    # Validate amount
    amount_satang = request.amount_thb * 100
    if amount_satang < MIN_AMOUNT_SATANG:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum amount is {MIN_AMOUNT_SATANG // 100} THB"
        )

    # Calculate pages
    pages_to_receive = calculate_pages_from_amount(amount_satang)

    # Generate reference ID
    reference_id = f"scanper_{line_user_id[:8]}_{uuid.uuid4().hex[:8]}"

    logger.info(f"Creating PromptPay charge for {line_user_id}: {amount_satang} satang, {pages_to_receive} pages")

    # Create PromptPay charge via Beam
    beam_response = await create_beam_charge(amount_satang, reference_id)

    charge_id = beam_response.get("chargeId")
    action_required = beam_response.get("actionRequired", "NONE")

    # Get QR code from PromptPay response
    qr_code = None
    if action_required == "ENCODED_IMAGE":
        qr_code = beam_response.get("encodedImage")

    logger.info(f"Beam response action: {action_required}, has QR: {qr_code is not None}")

    # Save payment record
    payment = Payment(
        charge_id=charge_id,
        reference_id=reference_id,
        line_user_id=line_user_id,
        amount_satang=amount_satang,
        pages_purchased=pages_to_receive,
        status=PaymentStatus.PENDING,
    )
    await payment.insert()

    logger.info(f"Payment created: {charge_id}, action: {action_required}")

    return CreateChargeResponse(
        charge_id=charge_id,
        reference_id=reference_id,
        amount_satang=amount_satang,
        pages_to_receive=pages_to_receive,
        action_required=action_required,
        redirect_url=None,  # Not used for PromptPay
        qr_code=qr_code,
    )


@router.get("/status/{charge_id}")
async def get_payment_status(
    charge_id: str,
    authorization: str = Header(..., description="Bearer <LINE_ACCESS_TOKEN>"),
):
    """Get payment status by charge ID."""
    # Verify LINE token
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    access_token = authorization[7:]
    profile = await verify_line_access_token(access_token)
    line_user_id = profile.get("userId")

    # Find payment
    payment = await Payment.find_one(Payment.charge_id == charge_id)

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Verify ownership
    if payment.line_user_id != line_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    return {
        "charge_id": payment.charge_id,
        "status": payment.status,
        "amount_thb": payment.amount_satang / 100,
        "pages_purchased": payment.pages_purchased,
        "created_at": payment.created_at.isoformat(),
    }


@router.get("/history", response_model=List[PaymentHistoryItem])
async def get_payment_history(
    authorization: str = Header(..., description="Bearer <LINE_ACCESS_TOKEN>"),
):
    """Get user's payment history."""
    # Verify LINE token
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    access_token = authorization[7:]
    profile = await verify_line_access_token(access_token)
    line_user_id = profile.get("userId")

    # Get payments
    payments = await Payment.find(
        Payment.line_user_id == line_user_id
    ).sort(-Payment.created_at).limit(20).to_list()

    return [
        PaymentHistoryItem(
            charge_id=p.charge_id,
            amount_thb=p.amount_satang / 100,
            pages_purchased=p.pages_purchased,
            status=p.status.value,
            created_at=p.created_at.isoformat(),
            payment_method=p.payment_method_type,
        )
        for p in payments
    ]


@router.post("/webhook/beam")
async def beam_webhook(request: Request):
    """
    Handle Beam webhook for charge.succeeded events.

    This endpoint is called by Beam when a payment is completed.
    """
    # Get raw body for signature verification
    body = await request.body()

    # Get headers
    signature = request.headers.get("x-beam-signature", "")
    event_type = request.headers.get("x-beam-event", "")

    logger.info(f"Received Beam webhook: {event_type}")

    # Verify signature
    if not verify_beam_signature(body, signature):
        logger.warning("Invalid Beam webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    # Handle charge.succeeded
    if event_type == "charge.succeeded":
        charge_id = payload.get("chargeId")
        status = payload.get("status")

        logger.info(f"Processing charge.succeeded: {charge_id}, status: {status}")

        # Find payment record
        payment = await Payment.find_one(Payment.charge_id == charge_id)

        if not payment:
            logger.warning(f"Payment not found for charge: {charge_id}")
            return {"status": "ok", "message": "Payment not found"}

        if payment.status == PaymentStatus.SUCCEEDED:
            logger.info(f"Payment already processed: {charge_id}")
            return {"status": "ok", "message": "Already processed"}

        # Update payment record
        payment.status = PaymentStatus.SUCCEEDED
        payment.completed_at = datetime.utcnow()
        payment.updated_at = datetime.utcnow()

        # Extract payment method info
        payment_method = payload.get("paymentMethod", {})
        payment.payment_method_type = payment_method.get("paymentMethodType")
        if payment_method.get("card"):
            payment.card_last4 = payment_method["card"].get("last4")
            payment.card_brand = payment_method["card"].get("brand")

        await payment.save()

        # Add pages to user's quota
        user = await user_repository.get_user_by_line_id(payment.line_user_id)
        if user:
            user.ocr_limit += payment.pages_purchased
            await user.save()
            logger.info(
                f"Added {payment.pages_purchased} pages to user {payment.line_user_id}, "
                f"new limit: {user.ocr_limit}"
            )
        else:
            logger.warning(f"User not found: {payment.line_user_id}")

        return {"status": "ok", "message": "Payment processed"}

    # Handle other events
    logger.info(f"Unhandled webhook event: {event_type}")
    return {"status": "ok", "message": f"Event {event_type} acknowledged"}
