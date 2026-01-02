"""Data access repositories."""

from app.repositories.user_repository import UserRepository, user_repository
from app.repositories.message_repository import MessageRepository, message_repository

__all__ = ["UserRepository", "MessageRepository", "user_repository", "message_repository"]
