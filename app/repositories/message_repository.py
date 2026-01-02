"""Repository for Message database operations."""

import logging
from typing import List, Optional, Dict, Any

from app.models.message import Message, MessageType
from app.models.user import User

logger = logging.getLogger(__name__)


class MessageRepository:
    """Repository for Message database operations."""

    @staticmethod
    async def create_message(
        user: User,
        message_type: MessageType,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        line_message_id: Optional[str] = None,
    ) -> Message:
        """
        Create and save a new message.

        Args:
            user: User document
            message_type: Type of message (text/image/pdf)
            content: Message content or extracted text
            metadata: Additional metadata (file size, processing time, etc.)
            line_message_id: LINE message ID

        Returns:
            Created Message document
        """
        try:
            message = Message(
                user=user,
                message_type=message_type,
                content=content,
                metadata=metadata or {},
                line_message_id=line_message_id,
            )
            await message.insert()
            logger.info(f"Message saved: user={user.line_user_id}, type={message_type}")
            return message

        except Exception as e:
            logger.error(f"Error creating message: {e}", exc_info=True)
            raise

    @staticmethod
    async def get_user_messages(
        user: User, message_type: Optional[MessageType] = None, limit: int = 20
    ) -> List[Message]:
        """
        Get messages for a user, optionally filtered by type.

        Args:
            user: User document
            message_type: Optional filter by message type
            limit: Maximum number of messages to return

        Returns:
            List of Message documents, newest first
        """
        try:
            query = Message.find(Message.user.id == user.id)

            if message_type:
                query = query.find(Message.message_type == message_type)

            messages = await query.sort(-Message.timestamp).limit(limit).to_list()

            logger.info(f"Retrieved {len(messages)} messages for user {user.line_user_id}")
            return messages

        except Exception as e:
            logger.error(f"Error retrieving messages: {e}", exc_info=True)
            return []

    @staticmethod
    async def get_text_messages_for_chat(user: User, limit: int = 20) -> List[Message]:
        """
        Get text messages for chat history (excludes OCR messages).

        Args:
            user: User document
            limit: Maximum number of messages

        Returns:
            List of text Message documents, oldest first
        """
        try:
            messages = (
                await Message.find(
                    Message.user.id == user.id, Message.message_type == MessageType.TEXT
                )
                .sort(Message.timestamp)
                .limit(limit)
                .to_list()
            )

            return messages

        except Exception as e:
            logger.error(f"Error retrieving chat messages: {e}", exc_info=True)
            return []


# Singleton instance
message_repository = MessageRepository()
