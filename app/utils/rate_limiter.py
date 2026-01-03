"""Simple in-memory rate limiter for webhook handlers."""

import time
from collections import defaultdict
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Simple sliding window rate limiter.
    Tracks requests per user to prevent abuse.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed per window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Store: user_id -> list of timestamps
        self.requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, user_id: str) -> Tuple[bool, int]:
        """
        Check if request from user is allowed.

        Args:
            user_id: User identifier

        Returns:
            Tuple of (is_allowed, requests_remaining)
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Clean old requests
        self.requests[user_id] = [
            ts for ts in self.requests[user_id] if ts > cutoff
        ]

        current_count = len(self.requests[user_id])

        if current_count >= self.max_requests:
            logger.warning(
                f"Rate limit exceeded for user {user_id}: "
                f"{current_count}/{self.max_requests} requests in {self.window_seconds}s"
            )
            return False, 0

        # Add current request
        self.requests[user_id].append(now)
        remaining = self.max_requests - current_count - 1

        return True, remaining

    def cleanup(self):
        """Clean up old entries to prevent memory leak."""
        now = time.time()
        cutoff = now - self.window_seconds

        for user_id in list(self.requests.keys()):
            self.requests[user_id] = [
                ts for ts in self.requests[user_id] if ts > cutoff
            ]
            if not self.requests[user_id]:
                del self.requests[user_id]

        logger.debug(f"Rate limiter cleanup: {len(self.requests)} active users")


# Global rate limiters for different message types
text_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)  # 10 messages/minute
image_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)  # 5 images/minute
pdf_rate_limiter = RateLimiter(max_requests=3, window_seconds=60)  # 3 PDFs/minute
