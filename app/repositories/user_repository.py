"""Repository for User database operations."""

import logging
from datetime import datetime
from typing import Optional, Tuple

from app.models.user import User

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for User database operations."""

    @staticmethod
    async def get_or_create_user(line_user_id: str) -> User:
        """
        Get existing user or create new one if first time.

        Args:
            line_user_id: LINE user ID from event.source.user_id

        Returns:
            User document
        """
        try:
            # Try to find existing user
            user = await User.find_one(User.line_user_id == line_user_id)

            if user:
                # Update last seen
                user.last_seen_at = datetime.utcnow()
                await user.save()
                logger.info(f"Existing user found: {line_user_id}")
                return user

            # Create new user
            user = User(line_user_id=line_user_id)
            await user.insert()
            logger.info(f"New user created: {line_user_id}")
            return user

        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}", exc_info=True)
            raise

    @staticmethod
    async def increment_message_count(user: User) -> None:
        """Increment user's message count."""
        try:
            user.message_count += 1
            await user.save()
        except Exception as e:
            logger.error(f"Error incrementing message count: {e}", exc_info=True)

    @staticmethod
    async def check_ocr_limit(user: User) -> Tuple[bool, int, int]:
        """
        Check if user has reached their OCR limit.

        Returns:
            Tuple of (is_allowed, remaining, limit)
        """
        return (
            not user.is_ocr_limit_reached,
            user.ocr_remaining,
            user.ocr_limit
        )

    @staticmethod
    async def increment_ocr_count(user: User, pages: int = 1) -> Tuple[int, int]:
        """
        Increment user's OCR count (both session and total).

        Args:
            user: User document
            pages: Number of pages processed (default 1)

        Returns:
            Tuple of (new_session_count, remaining)
        """
        try:
            user.ocr_count_session += pages
            user.ocr_count_total += pages
            await user.save()
            logger.info(
                f"OCR count updated for {user.line_user_id}: "
                f"session={user.ocr_count_session}/{user.ocr_limit}, "
                f"total={user.ocr_count_total}"
            )
            return user.ocr_count_session, user.ocr_remaining
        except Exception as e:
            logger.error(f"Error incrementing OCR count: {e}", exc_info=True)
            return user.ocr_count_session, user.ocr_remaining

    @staticmethod
    async def reset_ocr_session(user: User) -> None:
        """Reset user's OCR session count (admin function)."""
        try:
            user.ocr_count_session = 0
            await user.save()
            logger.info(f"OCR session reset for {user.line_user_id}")
        except Exception as e:
            logger.error(f"Error resetting OCR session: {e}", exc_info=True)

    @staticmethod
    async def set_ocr_limit(user: User, new_limit: int) -> None:
        """Set user's OCR limit (admin function)."""
        try:
            user.ocr_limit = new_limit
            await user.save()
            logger.info(f"OCR limit set to {new_limit} for {user.line_user_id}")
        except Exception as e:
            logger.error(f"Error setting OCR limit: {e}", exc_info=True)

    @staticmethod
    async def get_user_by_line_id(line_user_id: str) -> Optional[User]:
        """Get user by LINE user ID (for admin functions)."""
        try:
            return await User.find_one(User.line_user_id == line_user_id)
        except Exception as e:
            logger.error(f"Error getting user: {e}", exc_info=True)
            return None

    @staticmethod
    async def update_display_name(user: User, new_display_name: str) -> User:
        """
        Update user's display name.

        Args:
            user: User document
            new_display_name: New display name to set

        Returns:
            Updated user document
        """
        try:
            user.display_name = new_display_name.strip()
            await user.save()
            logger.info(f"Display name updated for {user.line_user_id}: {new_display_name}")
            return user
        except Exception as e:
            logger.error(f"Error updating display name: {e}", exc_info=True)
            raise


# Singleton instance
user_repository = UserRepository()
