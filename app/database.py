"""Database initialization and connection management."""

import logging
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.config import settings
from app.models import User, Message, Payment

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager."""

    client: AsyncIOMotorClient = None

    @classmethod
    async def connect_db(cls):
        """Connect to MongoDB and initialize Beanie with connection pooling."""
        try:
            # Configure connection pool for better concurrency
            cls.client = AsyncIOMotorClient(
                settings.MONGODB_URL,
                maxPoolSize=50,  # Maximum connections in pool
                minPoolSize=10,  # Minimum connections to maintain
                maxIdleTimeMS=45000,  # Close idle connections after 45s
                serverSelectionTimeoutMS=5000,  # Timeout for server selection
                connectTimeoutMS=10000,  # Timeout for initial connection
                socketTimeoutMS=45000,  # Timeout for socket operations
            )

            # Test connection
            await cls.client.admin.command("ping")
            logger.info(f"Connected to MongoDB Atlas: {settings.MONGODB_DB_NAME} (pool: 10-50 connections)")

            # Initialize Beanie with document models
            await init_beanie(
                database=cls.client[settings.MONGODB_DB_NAME], document_models=[User, Message, Payment]
            )

            logger.info("Beanie ODM initialized successfully")

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}", exc_info=True)
            raise

    @classmethod
    async def close_db(cls):
        """Close database connection."""
        if cls.client:
            cls.client.close()
            logger.info("MongoDB connection closed")


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan context manager for database connection."""
    # Startup
    await Database.connect_db()
    yield
    # Shutdown
    await Database.close_db()


# Convenience access
db = Database()
