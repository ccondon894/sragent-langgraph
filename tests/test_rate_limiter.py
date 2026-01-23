"""
Tests for rate limiting functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from rate_limiter import RateLimitConfig, SessionRateLimiter


@pytest.fixture
def session_state():
    """Mock Streamlit session_state object."""
    state = MagicMock()
    state.query_timestamps = []
    state.queries_in_session = 0
    return state


@pytest.fixture
def rate_limiter(session_state):
    """Create a rate limiter instance with default config."""
    return SessionRateLimiter(session_state)


class TestRateLimitConfig:
    """Test RateLimitConfig dataclass."""

    def test_default_config(self):
        """Test that default config has expected values."""
        config = RateLimitConfig()
        assert config.max_queries_per_session == 10
        assert config.max_queries_per_hour == 50
        assert config.cooldown_seconds == 30

    def test_custom_config(self):
        """Test that custom config values are respected."""
        config = RateLimitConfig(
            max_queries_per_session=5,
            max_queries_per_hour=20,
            cooldown_seconds=10
        )
        assert config.max_queries_per_session == 5
        assert config.max_queries_per_hour == 20
        assert config.cooldown_seconds == 10


class TestSessionRateLimiterInitialization:
    """Test rate limiter initialization."""

    def test_initializes_session_state(self, session_state):
        """Test that init creates required session state variables."""
        limiter = SessionRateLimiter(session_state)
        assert "query_timestamps" in session_state
        assert "queries_in_session" in session_state
        assert session_state.query_timestamps == []
        assert session_state.queries_in_session == 0

    def test_preserves_existing_session_state(self, session_state):
        """Test that init doesn't overwrite existing session state."""
        session_state.query_timestamps = [datetime.now()]
        session_state.queries_in_session = 5

        limiter = SessionRateLimiter(session_state)
        assert len(session_state.query_timestamps) == 1
        assert session_state.queries_in_session == 5


class TestCanQuery:
    """Test the can_query method."""

    def test_allows_first_query(self, rate_limiter):
        """Test that first query is always allowed."""
        allowed, reason = rate_limiter.can_query()
        assert allowed is True
        assert reason == ""

    def test_allows_multiple_queries_within_limits(self, rate_limiter):
        """Test that queries within all limits are allowed."""
        for i in range(5):
            allowed, reason = rate_limiter.can_query()
            assert allowed is True, f"Query {i+1} should be allowed"
            rate_limiter.record_query()

    @patch("rate_limiter.datetime")
    def test_blocks_cooldown(self, mock_datetime, session_state):
        """Test that cooldown blocks queries."""
        config = RateLimitConfig(cooldown_seconds=30)
        limiter = SessionRateLimiter(session_state, config)

        # Record first query at time 0
        now = datetime(2026, 1, 22, 12, 0, 0)
        mock_datetime.now.return_value = now
        allowed, reason = limiter.can_query()
        assert allowed is True
        limiter.record_query()

        # Try query at time 15 seconds (should be blocked)
        mock_datetime.now.return_value = now + timedelta(seconds=15)
        allowed, reason = limiter.can_query()
        assert allowed is False
        assert "Cooldown active" in reason

        # Try query at time 30 seconds (should be allowed)
        mock_datetime.now.return_value = now + timedelta(seconds=30)
        allowed, reason = limiter.can_query()
        assert allowed is True

    def test_blocks_session_limit(self, session_state):
        """Test that session limit blocks queries."""
        config = RateLimitConfig(max_queries_per_session=3)
        limiter = SessionRateLimiter(session_state, config)

        # Record 3 queries
        for i in range(3):
            allowed, reason = limiter.can_query()
            assert allowed is True
            limiter.record_query()

        # 4th query should be blocked
        allowed, reason = limiter.can_query()
        assert allowed is False
        assert "Session limit reached" in reason

    @patch("rate_limiter.datetime")
    def test_blocks_hourly_limit(self, mock_datetime, session_state):
        """Test that hourly limit blocks queries."""
        config = RateLimitConfig(
            max_queries_per_session=100,  # High to not interfere
            max_queries_per_hour=3,
            cooldown_seconds=0  # Disable cooldown for this test
        )
        limiter = SessionRateLimiter(session_state, config)

        base_time = datetime(2026, 1, 22, 12, 0, 0)
        mock_datetime.now.return_value = base_time

        # Record 3 queries in the hour
        for i in range(3):
            mock_datetime.now.return_value = base_time + timedelta(minutes=i)
            allowed, reason = limiter.can_query()
            assert allowed is True
            limiter.record_query()

        # 4th query should be blocked
        mock_datetime.now.return_value = base_time + timedelta(minutes=3)
        allowed, reason = limiter.can_query()
        assert allowed is False
        assert "Hourly limit reached" in reason

    @patch("rate_limiter.datetime")
    def test_hourly_limit_resets_after_hour(self, mock_datetime, session_state):
        """Test that hourly limit resets after 1 hour."""
        config = RateLimitConfig(
            max_queries_per_session=100,
            max_queries_per_hour=2,
            cooldown_seconds=0
        )
        limiter = SessionRateLimiter(session_state, config)

        base_time = datetime(2026, 1, 22, 12, 0, 0)
        mock_datetime.now.return_value = base_time

        # Record 2 queries
        for i in range(2):
            mock_datetime.now.return_value = base_time + timedelta(seconds=i)
            limiter.record_query()

        # Move 1 hour forward and try again
        mock_datetime.now.return_value = base_time + timedelta(hours=1, seconds=1)
        allowed, reason = limiter.can_query()
        assert allowed is True
        assert reason == ""


class TestRecordQuery:
    """Test the record_query method."""

    def test_records_timestamp(self, rate_limiter):
        """Test that record_query adds timestamp."""
        before = datetime.now()
        rate_limiter.record_query()
        after = datetime.now()

        assert len(rate_limiter.session_state.query_timestamps) == 1
        recorded = rate_limiter.session_state.query_timestamps[0]
        assert before <= recorded <= after

    def test_increments_session_count(self, rate_limiter):
        """Test that record_query increments session count."""
        assert rate_limiter.session_state.queries_in_session == 0
        rate_limiter.record_query()
        assert rate_limiter.session_state.queries_in_session == 1
        rate_limiter.record_query()
        assert rate_limiter.session_state.queries_in_session == 2

    def test_multiple_records(self, rate_limiter):
        """Test recording multiple queries."""
        for i in range(5):
            rate_limiter.record_query()

        assert len(rate_limiter.session_state.query_timestamps) == 5
        assert rate_limiter.session_state.queries_in_session == 5


class TestGetRemainingQueries:
    """Test the get_remaining_queries method."""

    def test_initial_remaining(self, rate_limiter):
        """Test remaining queries at start."""
        remaining = rate_limiter.get_remaining_queries()
        assert remaining["remaining_session"] == 10
        assert remaining["remaining_hour"] == 50
        assert remaining["cooldown_active"] is False
        assert remaining["seconds_until_next"] == 0

    def test_session_remaining_after_query(self, rate_limiter):
        """Test session remaining decreases after queries."""
        rate_limiter.record_query()
        remaining = rate_limiter.get_remaining_queries()
        assert remaining["remaining_session"] == 9

        rate_limiter.record_query()
        remaining = rate_limiter.get_remaining_queries()
        assert remaining["remaining_session"] == 8

    @patch("rate_limiter.datetime")
    def test_hour_remaining_after_query(self, mock_datetime, session_state):
        """Test hourly remaining decreases after queries."""
        config = RateLimitConfig(cooldown_seconds=0)
        limiter = SessionRateLimiter(session_state, config)

        now = datetime(2026, 1, 22, 12, 0, 0)
        mock_datetime.now.return_value = now

        limiter.record_query()
        remaining = limiter.get_remaining_queries()
        assert remaining["remaining_hour"] == 49

    @patch("rate_limiter.datetime")
    def test_cooldown_active_detection(self, mock_datetime, session_state):
        """Test that cooldown_active is detected correctly."""
        config = RateLimitConfig(cooldown_seconds=30)
        limiter = SessionRateLimiter(session_state, config)

        now = datetime(2026, 1, 22, 12, 0, 0)
        mock_datetime.now.return_value = now
        limiter.record_query()

        # Check at 15 seconds
        mock_datetime.now.return_value = now + timedelta(seconds=15)
        remaining = limiter.get_remaining_queries()
        assert remaining["cooldown_active"] is True
        assert 14 <= remaining["seconds_until_next"] <= 16

        # Check at 30 seconds
        mock_datetime.now.return_value = now + timedelta(seconds=30)
        remaining = limiter.get_remaining_queries()
        assert remaining["cooldown_active"] is False
        assert remaining["seconds_until_next"] == 0

    def test_returns_zero_when_exceeded(self, session_state):
        """Test that remaining returns 0 when limits exceeded."""
        config = RateLimitConfig(max_queries_per_session=2)
        limiter = SessionRateLimiter(session_state, config)

        limiter.record_query()
        limiter.record_query()
        remaining = limiter.get_remaining_queries()
        assert remaining["remaining_session"] == 0


class TestResetSession:
    """Test the reset_session method."""

    def test_resets_session_count(self, rate_limiter):
        """Test that reset_session clears session count."""
        rate_limiter.record_query()
        rate_limiter.record_query()
        assert rate_limiter.session_state.queries_in_session == 2

        rate_limiter.reset_session()
        assert rate_limiter.session_state.queries_in_session == 0

    def test_preserves_timestamps(self, rate_limiter):
        """Test that reset_session doesn't clear timestamps."""
        rate_limiter.record_query()
        timestamps_before = len(rate_limiter.session_state.query_timestamps)

        rate_limiter.reset_session()
        assert len(rate_limiter.session_state.query_timestamps) == timestamps_before


class TestEndToEndLimiting:
    """End-to-end tests for complete limiting scenarios."""

    def test_full_workflow(self, rate_limiter):
        """Test a complete workflow of queries and limits."""
        # First few queries should succeed
        for i in range(3):
            allowed, reason = rate_limiter.can_query()
            assert allowed is True
            rate_limiter.record_query()

        remaining = rate_limiter.get_remaining_queries()
        assert remaining["remaining_session"] == 7

    @patch("rate_limiter.datetime")
    def test_cooldown_then_success(self, mock_datetime, session_state):
        """Test recovery after cooldown."""
        config = RateLimitConfig(cooldown_seconds=30)
        limiter = SessionRateLimiter(session_state, config)

        now = datetime(2026, 1, 22, 12, 0, 0)
        mock_datetime.now.return_value = now

        # First query
        limiter.record_query()

        # Too soon
        mock_datetime.now.return_value = now + timedelta(seconds=15)
        allowed, reason = limiter.can_query()
        assert allowed is False

        # After cooldown
        mock_datetime.now.return_value = now + timedelta(seconds=30)
        allowed, reason = limiter.can_query()
        assert allowed is True
        limiter.record_query()

        assert limiter.session_state.queries_in_session == 2
