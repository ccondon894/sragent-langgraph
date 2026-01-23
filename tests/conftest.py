"""
Pytest configuration and fixtures for SRA agent tests.

Provides:
- Cost tracking to monitor API usage during tests
- Mock LLM and BigQuery fixtures
- Common test data and utilities
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mocks.fake_llm import TrackedFakeLLM
from tests.mocks.fake_bigquery import FakeClient


# ============================================================================
# Cost Tracking Configuration
# ============================================================================

COST_LIMITS = {
    "max_gemini_calls_per_run": 10,
    "max_bigquery_bytes_per_run": 50 * 1024 * 1024,  # 50 MB
    "max_total_cost_usd": 0.50,
}


class CostTracker:
    """Track and enforce API cost limits during tests."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset cost tracking for new test."""
        self.gemini_calls = 0
        self.bigquery_bytes = 0
        self.total_cost_usd = 0.0
        self.start_time = datetime.now()

    def record_gemini_call(self, cost_usd: float = 0.001):
        """Record a Gemini API call."""
        self.gemini_calls += 1
        self.total_cost_usd += cost_usd

    def record_bigquery_bytes(self, bytes_processed: int, cost_usd: float = 0.0):
        """Record BigQuery bytes processed."""
        self.bigquery_bytes += bytes_processed
        self.total_cost_usd += cost_usd

    def check_limits(self):
        """Check if any limits have been exceeded."""
        if self.gemini_calls > COST_LIMITS["max_gemini_calls_per_run"]:
            raise RuntimeError(
                f"Exceeded Gemini call limit: {self.gemini_calls} "
                f"> {COST_LIMITS['max_gemini_calls_per_run']}"
            )

        if self.bigquery_bytes > COST_LIMITS["max_bigquery_bytes_per_run"]:
            raise RuntimeError(
                f"Exceeded BigQuery bytes limit: {self.bigquery_bytes} "
                f"> {COST_LIMITS['max_bigquery_bytes_per_run']}"
            )

        if self.total_cost_usd > COST_LIMITS["max_total_cost_usd"]:
            raise RuntimeError(
                f"Exceeded cost limit: ${self.total_cost_usd:.2f} "
                f"> ${COST_LIMITS['max_total_cost_usd']:.2f}"
            )

    def get_summary(self) -> dict:
        """Get cost summary for test report."""
        elapsed = datetime.now() - self.start_time
        return {
            "gemini_calls": self.gemini_calls,
            "bigquery_bytes": self.bigquery_bytes,
            "total_cost_usd": self.total_cost_usd,
            "elapsed_seconds": elapsed.total_seconds(),
        }


# Global cost tracker
_cost_tracker = CostTracker()


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_cost_tracking():
    """Reset cost tracking before each test."""
    _cost_tracker.reset()
    TrackedFakeLLM.reset_cost_tracking()
    yield
    # Check limits after test
    _cost_tracker.check_limits()


@pytest.fixture
def cost_tracker():
    """Provide access to cost tracker in tests."""
    return _cost_tracker


@pytest.fixture
def fake_llm():
    """Provide a fake LLM for testing."""
    TrackedFakeLLM.reset_cost_tracking()
    return TrackedFakeLLM()


@pytest.fixture
def fake_bigquery_client():
    """Provide a fake BigQuery client for testing."""
    return FakeClient(project="test-project")


@pytest.fixture
def mock_streamlit_session_state():
    """Provide mock Streamlit session state."""
    # Use a dictionary-based mock that supports 'in' operator
    class MockSessionState(dict):
        """Mock session state that acts like both dict and object."""
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError:
                raise AttributeError(name)

        def __setattr__(self, name, value):
            self[name] = value

        def __contains__(self, name):
            return dict.__contains__(self, name)

    state = MockSessionState()
    state['query_timestamps'] = []
    state['queries_in_session'] = 0
    state['credentials_loaded'] = False
    return state


@pytest.fixture
def sample_sra_query_state():
    """Provide sample SRA query state for testing."""
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content="Find human cancer RNA-seq data")],
        "organism": None,
        "library_source": None,
        "platform": None,
        "keywords": [],
        "query_results": None,
        "total_count": None,
        "error_message": None,
        "retry_count": 0,
    }


@pytest.fixture
def mock_pydantic_extraction_model():
    """Provide a mock Pydantic model for parameter extraction."""
    from pydantic import BaseModel

    class SRAExtraction(BaseModel):
        organism: str = None
        library_source: str = None
        platform: str = None
        keywords: list = []

    return SRAExtraction


@pytest.fixture
def mock_pydantic_sql_model():
    """Provide a mock Pydantic model for SQL compilation."""
    from pydantic import BaseModel

    class SQLComponents(BaseModel):
        where_clause: str
        columns: list

    return SQLComponents


# ============================================================================
# Hooks
# ============================================================================


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "live: mark test as using live APIs (deselect with '-m \"not live\"')"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Add markers to tests based on naming conventions."""
    for item in items:
        # Mark live API tests
        if "e2e" in item.nodeid or "live" in item.nodeid:
            item.add_marker(pytest.mark.live)

        # Mark slow tests
        if "e2e" in item.nodeid:
            item.add_marker(pytest.mark.slow)


# ============================================================================
# Test Data
# ============================================================================

SAMPLE_ORGANISMS = [
    "Homo sapiens",
    "Mus musculus",
    "Drosophila melanogaster",
    "Caenorhabditis elegans",
]

SAMPLE_LIBRARY_SOURCES = [
    "TRANSCRIPTOMIC",
    "GENOMIC",
    "METAGENOMIC",
]

SAMPLE_PLATFORMS = [
    "ILLUMINA",
    "OXFORD_NANOPORE",
    "PACBIO",
]

SAMPLE_KEYWORDS = [
    "cancer",
    "lung",
    "p53",
    "mutation",
    "tumor",
]
