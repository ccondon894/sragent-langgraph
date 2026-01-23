"""
Fake LLM implementation that tracks API costs for testing.

This module provides a mock LLM that:
- Returns predefined responses without calling Gemini API
- Tracks number of calls and estimated costs
"""

from typing import Any, Dict, List, Optional


class TrackedFakeLLM:
    """
    Fake LLM that tracks API calls without making real requests.

    Useful for:
    - Unit testing agent logic without API costs
    - Predicting and monitoring API call patterns
    - Testing error handling
    """

    # Cost tracking (class-level to persist across instances)
    call_count: int = 0
    estimated_cost_usd: float = 0.0

    # Mock responses for different operations
    mock_responses: Dict[str, Any] = {
        "param_extraction": {
            "organism": "Homo sapiens",
            "library_source": "TRANSCRIPTOMIC",
            "platform": "ILLUMINA",
            "keywords": ["cancer", "lung"]
        },
        "sql_generation": "organism = 'Homo sapiens' AND librarysource = 'TRANSCRIPTOMIC'",
        "clarification": "What organism are you interested in? (e.g., human, mouse)",
        "response": "Found 42 matching samples with your criteria."
    }

    # Pricing (Gemini API as of 2025)
    # Input: $0.075/1M tokens, Output: $0.3/1M tokens
    COST_PER_1K_INPUT_TOKENS = 0.000075
    COST_PER_1K_OUTPUT_TOKENS = 0.0003

    def __init__(self, response_type: str = "default", **kwargs):
        """
        Initialize fake LLM.

        Args:
            response_type: Type of mock response to return
        """
        self.response_type = response_type
        self._call_count = 0

    def invoke(self, input_data: Any, **kwargs) -> Any:
        """
        Generate a response and track the cost.

        Args:
            input_data: Input messages or data
            **kwargs: Additional arguments

        Returns:
            Mock response
        """
        # Track the call
        self._call_count += 1
        TrackedFakeLLM.call_count += 1

        # Estimate token usage
        avg_input_tokens = 50  # Rough estimate
        avg_output_tokens = 100  # Rough estimate

        # Calculate estimated cost
        input_cost = (avg_input_tokens / 1000) * self.COST_PER_1K_INPUT_TOKENS
        output_cost = (avg_output_tokens / 1000) * self.COST_PER_1K_OUTPUT_TOKENS
        call_cost = input_cost + output_cost
        TrackedFakeLLM.estimated_cost_usd += call_cost

        # Generate mock response
        response_text = self._get_mock_response(input_data)

        # Return as a mock object with content attribute
        class MockResponse:
            def __init__(self, content):
                self.content = content

        return MockResponse(response_text)

    def _get_mock_response(self, input_data: Any) -> str:
        """Get appropriate mock response based on input."""
        if isinstance(input_data, dict):
            input_str = str(input_data).lower()
        else:
            input_str = str(input_data).lower()

        if "organism" in input_str or "parameter" in input_str:
            return str(self.mock_responses["param_extraction"])
        elif "sql" in input_str or "where" in input_str:
            return self.mock_responses["sql_generation"]
        elif "missing" in input_str or "clarif" in input_str:
            return self.mock_responses["clarification"]
        else:
            return self.mock_responses["response"]

    @classmethod
    def reset_cost_tracking(cls):
        """Reset global cost tracking for new test."""
        cls.call_count = 0
        cls.estimated_cost_usd = 0.0

    @classmethod
    def get_total_cost(cls) -> float:
        """Get estimated total API cost for all calls made."""
        return cls.estimated_cost_usd

    @classmethod
    def get_call_count(cls) -> int:
        """Get total number of LLM calls made."""
        return cls.call_count
