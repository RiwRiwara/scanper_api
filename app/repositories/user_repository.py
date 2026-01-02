"""Repository for User database operations."""

import logging
from datetime import datetime
from typing import Optional

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


# Singleton instance
user_repository = UserRepository()
