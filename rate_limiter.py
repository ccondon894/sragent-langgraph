"""
Rate limiting infrastructure for the SRA Streamlit app.

Provides session-based and hourly rate limiting to protect against runaway API costs.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Tuple


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting behavior."""

    max_queries_per_session: int = 10
    max_queries_per_hour: int = 50
    cooldown_seconds: int = 30


class SessionRateLimiter:
    """
    Rate limiter using Streamlit session state for persistence across reruns.

    Tracks:
    - Queries per session (reset on new session)
    - Queries per hour (rolling window)
    - Cooldown between consecutive queries
    """

    def __init__(self, session_state, config: RateLimitConfig = None):
        """
        Initialize the rate limiter.

        Args:
            session_state: Streamlit session_state object for persistence
            config: RateLimitConfig instance (uses defaults if None)
        """
        self.session_state = session_state
        self.config = config or RateLimitConfig()
        self._init_session_state()

    def _init_session_state(self):
        """Initialize session state variables if not already present."""
        if "query_timestamps" not in self.session_state:
            self.session_state.query_timestamps = []
        if "queries_in_session" not in self.session_state:
            self.session_state.queries_in_session = 0

    def can_query(self) -> Tuple[bool, str]:
        """
        Check if a query is allowed.

        Returns:
            (bool, str): (allowed, reason) tuple
                - allowed: True if query can proceed
                - reason: Explanation if blocked (empty string if allowed)
        """
        now = datetime.now()

        # Check cooldown
        if self.session_state.query_timestamps:
            last_query = self.session_state.query_timestamps[-1]
            elapsed = (now - last_query).total_seconds()

            if elapsed < self.config.cooldown_seconds:
                remaining = self.config.cooldown_seconds - elapsed
                return False, f"Cooldown active. Please wait {remaining:.0f} more seconds."

        # Check session limit
        if self.session_state.queries_in_session >= self.config.max_queries_per_session:
            return False, f"Session limit reached ({self.config.max_queries_per_session} queries). Please refresh to start a new session."

        # Check hourly limit
        cutoff = now - timedelta(hours=1)
        recent_queries = [ts for ts in self.session_state.query_timestamps if ts > cutoff]

        if len(recent_queries) >= self.config.max_queries_per_hour:
            return False, f"Hourly limit reached ({self.config.max_queries_per_hour} queries). Please try again later."

        return True, ""

    def record_query(self):
        """Record that a query was executed."""
        now = datetime.now()
        self.session_state.query_timestamps.append(now)
        self.session_state.queries_in_session += 1

    def get_remaining_queries(self) -> dict:
        """
        Get remaining query allowances.

        Returns:
            dict with keys:
                - remaining_session: Queries left in this session
                - remaining_hour: Queries left in the current hour
                - cooldown_active: Whether cooldown is currently active
                - seconds_until_next: Seconds until next query allowed (0 if allowed now)
        """
        now = datetime.now()

        # Session remaining
        remaining_session = max(
            0,
            self.config.max_queries_per_session - self.session_state.queries_in_session
        )

        # Hour remaining
        cutoff = now - timedelta(hours=1)
        recent_queries = [ts for ts in self.session_state.query_timestamps if ts > cutoff]
        remaining_hour = max(0, self.config.max_queries_per_hour - len(recent_queries))

        # Cooldown
        cooldown_active = False
        seconds_until_next = 0

        if self.session_state.query_timestamps:
            last_query = self.session_state.query_timestamps[-1]
            elapsed = (now - last_query).total_seconds()

            if elapsed < self.config.cooldown_seconds:
                cooldown_active = True
                seconds_until_next = self.config.cooldown_seconds - elapsed

        return {
            "remaining_session": remaining_session,
            "remaining_hour": remaining_hour,
            "cooldown_active": cooldown_active,
            "seconds_until_next": seconds_until_next,
        }

    def reset_session(self):
        """Reset session-level counters (used for testing or explicit reset)."""
        self.session_state.queries_in_session = 0
