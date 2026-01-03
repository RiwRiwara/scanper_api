"""LIFF Router for frontend user data access."""

import logging
import httpx
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from bson import ObjectId

from app.repositories.user_repository import user_repository
from app.repositories.message_repository import message_repository
from app.models.message import Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/liff", tags=["LIFF"])

# LINE API endpoint for verifying access token
LINE_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"
LINE_PROFILE_URL = "https://api.line.me/v2/profile"


class UserResponse(BaseModel):
    """Response model for user data."""
    line_user_id: str
    display_name: Optional[str] = None
    ocr_count_session: int
    ocr_limit: int
    ocr_remaining: int
    ocr_count_total: int
    message_count: int
    first_seen_at: str
    last_seen_at: str


class UserNotFoundResponse(BaseModel):
    """Response when user hasn't used the bot yet."""
    message: str
    line_user_id: str
    display_name: Optional[str] = None


class UpdateDisplayNameRequest(BaseModel):
    """Request model for updating display name."""
    display_name: str


class UpdateDisplayNameResponse(BaseModel):
    """Response model for display name update."""
    success: bool
    display_name: str
    message: str


async def verify_line_access_token(access_token: str) -> dict:
    """
    Verify LINE access token and get user profile.

    Args:
        access_token: LINE access token from LIFF

    Returns:
        User profile dict with userId, displayName, etc.

    Raises:
        HTTPException: If token is invalid
    """
    async with httpx.AsyncClient() as client:
        # First verify the token is valid
        verify_response = await client.get(
            LINE_VERIFY_URL,
            params={"access_token": access_token}
        )

        if verify_response.status_code != 200:
            logger.warning(f"Invalid access token: {verify_response.text}")
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired LINE access token"
            )

        # Get user profile
        profile_response = await client.get(
            LINE_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        if profile_response.status_code != 200:
            logger.warning(f"Failed to get profile: {profile_response.text}")
            raise HTTPException(
                status_code=401,
                detail="Failed to get user profile"
            )

        return profile_response.json()


@router.get("/user", response_model=UserResponse | UserNotFoundResponse)
async def get_user_data(
    authorization: str = Header(..., description="Bearer <LINE_ACCESS_TOKEN>")
):
    """
    Get user's OCR usage data.

    Requires LINE access token from LIFF SDK in Authorization header.
    Format: Bearer <access_token>
    """
    # Extract token from Bearer header
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be: Bearer <access_token>"
        )

    access_token = authorization[7:]  # Remove "Bearer " prefix

    # Verify token and get LINE profile
    profile = await verify_line_access_token(access_token)
    line_user_id = profile.get("userId")
    display_name = profile.get("displayName")

    logger.info(f"LIFF user lookup: {line_user_id} ({display_name})")

    # Get user from database
    user = await user_repository.get_user_by_line_id(line_user_id)

    if not user:
        # User hasn't used the bot yet
        return UserNotFoundResponse(
            message="You haven't used the OCR bot yet. Send an image or PDF to the LINE bot to start!",
            line_user_id=line_user_id,
            display_name=display_name
        )

    # Update display name if changed
    if display_name and user.display_name != display_name:
        user.display_name = display_name
        await user.save()

    return UserResponse(
        line_user_id=user.line_user_id,
        display_name=user.display_name or display_name,
        ocr_count_session=user.ocr_count_session,
        ocr_limit=user.ocr_limit,
        ocr_remaining=user.ocr_remaining,
        ocr_count_total=user.ocr_count_total,
        message_count=user.message_count,
        first_seen_at=user.first_seen_at.isoformat(),
        last_seen_at=user.last_seen_at.isoformat(),
    )


@router.patch("/user/display-name", response_model=UpdateDisplayNameResponse)
async def update_display_name(
    request: UpdateDisplayNameRequest,
    authorization: str = Header(..., description="Bearer <LINE_ACCESS_TOKEN>")
):
    """
    Update user's display name.

    Requires LINE access token from LIFF SDK in Authorization header.
    Format: Bearer <access_token>
    """
    # Extract token from Bearer header
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be: Bearer <access_token>"
        )

    access_token = authorization[7:]  # Remove "Bearer " prefix

    # Verify token and get LINE profile
    profile = await verify_line_access_token(access_token)
    line_user_id = profile.get("userId")

    logger.info(f"LIFF display name update for: {line_user_id}")

    # Validate display name
    new_display_name = request.display_name.strip()
    if not new_display_name:
        raise HTTPException(
            status_code=400,
            detail="Display name cannot be empty"
        )

    if len(new_display_name) > 50:
        raise HTTPException(
            status_code=400,
            detail="Display name cannot exceed 50 characters"
        )

    # Get user from database
    user = await user_repository.get_user_by_line_id(line_user_id)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please use the bot first."
        )

    # Update display name
    updated_user = await user_repository.update_display_name(user, new_display_name)

    return UpdateDisplayNameResponse(
        success=True,
        display_name=updated_user.display_name,
        message="Display name updated successfully"
    )


@router.get("/health")
async def liff_health():
    """Health check for LIFF endpoints."""
    return {"status": "ok", "service": "liff"}


class MessageContentResponse(BaseModel):
    """Response model for OCR message content."""
    id: str
    message_type: str
    content: str
    timestamp: str
    metadata: dict


@router.get("/message/{message_id}", response_model=MessageContentResponse)
async def get_message_content(
    message_id: str,
    authorization: str = Header(..., description="Bearer <LINE_ACCESS_TOKEN>")
):
    """
    Get full OCR message content by ID.

    Used by LIFF to display full OCR results when user clicks "ดูเพิ่มเติม".
    Requires LINE access token to verify user owns the message.
    """
    # Extract token from Bearer header
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be: Bearer <access_token>"
        )

    access_token = authorization[7:]

    # Verify token and get LINE profile
    profile = await verify_line_access_token(access_token)
    line_user_id = profile.get("userId")

    logger.info(f"LIFF message lookup: {message_id} by {line_user_id}")

    # Validate message_id format
    try:
        obj_id = ObjectId(message_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid message ID format")

    # Get message from database with linked user
    message = await Message.get(obj_id, fetch_links=True)

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Verify user owns this message
    if not message.user or message.user.line_user_id != line_user_id:
        raise HTTPException(status_code=403, detail="You don't have access to this message")

    return MessageContentResponse(
        id=str(message.id),
        message_type=message.message_type.value,
        content=message.content,
        timestamp=message.timestamp.isoformat(),
        metadata=message.metadata or {}
    )
