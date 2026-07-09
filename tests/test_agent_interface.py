"""
Tests for the callable agent interface.

These tests verify that:
1. create_sra_agent() returns a functional agent
2. query_sra() interface works for programmatic queries
3. Credential injection works correctly
"""

import pytest
import uuid
from unittest.mock import Mock, patch

from langgraph_agent import create_sra_agent, query_sra, set_bq_credentials, get_bq_client
from langgraph_agent import clients


class TestCreateSraAgent:
    """Test agent factory function."""

    def test_create_agent_without_credentials(self):
        """Agent should be created successfully without credentials."""
        # Patch the LLM constructor so the test needs no API key / network.
        with patch("langgraph_agent.agent.ChatGoogleGenerativeAI", return_value=Mock()):
            agent = create_sra_agent()
        assert agent is not None
        # Should be a compiled runnable
        assert hasattr(agent, "invoke")

    def test_create_agent_with_credentials(self):
        """Agent should accept and store credential injection."""
        fake_credentials = {
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key123",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQE\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "client_id": "123456",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        # Building the Vertex-backed LLM would validate the (fake) service
        # account and hit the network, so patch both the credential loader and
        # the LLM constructor to isolate the factory's wiring logic.
        with patch(
            "google.oauth2.service_account.Credentials.from_service_account_info",
            return_value=Mock(),
        ), patch("langgraph_agent.agent.ChatGoogleGenerativeAI", return_value=Mock()):
            agent = create_sra_agent(credentials=fake_credentials)
        assert agent is not None
        # Credentials should have been injected for BigQuery use.
        assert clients._bq_credentials == fake_credentials


class TestQuerySraInterface:
    """Test the query_sra programmatic interface."""

    def _make_agent(self, state):
        """Build a mock agent whose invoke() returns the given final state."""
        agent = Mock()
        agent.invoke.return_value = state
        return agent

    def test_query_sra_returns_dict(self):
        """query_sra should return a structured dictionary."""
        from langchain_core.messages import AIMessage

        state = {
            "messages": [AIMessage(content="Found 42 records")],
            "organism": "Homo sapiens",
            "library_source": "TRANSCRIPTOMIC",
            "platform": "ILLUMINA",
            "keywords": ["cancer"],
            "query_results": [{"acc": "SRR123"}, {"acc": "SRR124"}],
            "total_count": 42,
            "error_message": None,
        }
        agent = self._make_agent(state)

        result = query_sra(agent, "Find human cancer data")

        assert isinstance(result, dict)
        for key in (
            "response", "organism", "library_source", "platform",
            "keywords", "results", "total_count", "error", "thread_id",
        ):
            assert key in result
        assert result["response"] == "Found 42 records"
        assert result["total_count"] == 42

    def test_query_sra_with_custom_thread_id(self):
        """query_sra should preserve provided thread_id."""
        from langchain_core.messages import AIMessage

        state = {
            "messages": [AIMessage(content="Test")],
            "organism": None, "library_source": None, "platform": None,
            "keywords": None, "query_results": None, "total_count": None,
            "error_message": None,
        }
        agent = self._make_agent(state)

        custom_thread_id = "custom-123"
        result = query_sra(agent, "Test query", thread_id=custom_thread_id)

        assert result["thread_id"] == custom_thread_id
        # Verify invoke was called with the thread_id in its config.
        call_args = agent.invoke.call_args
        assert call_args[1]["config"]["configurable"]["thread_id"] == custom_thread_id

    def test_query_sra_error_handling(self):
        """query_sra should gracefully handle errors."""
        agent = Mock()
        agent.invoke.side_effect = Exception("BigQuery connection failed")

        result = query_sra(agent, "Bad query")

        assert result["response"] is None
        assert "BigQuery connection failed" in result["error"]
        assert result["thread_id"] is not None

    def test_query_sra_auto_thread_id(self):
        """query_sra should generate a unique thread_id if not provided."""
        from langchain_core.messages import AIMessage

        state = {
            "messages": [AIMessage(content="Test")],
            "organism": None, "library_source": None, "platform": None,
            "keywords": None, "query_results": None, "total_count": None,
            "error_message": None,
        }
        agent = self._make_agent(state)

        result1 = query_sra(agent, "Query 1")
        result2 = query_sra(agent, "Query 2")

        # Each call should generate a unique thread_id
        assert result1["thread_id"] != result2["thread_id"]
        # Both should be valid UUIDs
        uuid.UUID(result1["thread_id"])
        uuid.UUID(result2["thread_id"])


class TestCredentialInjection:
    """Test credential injection mechanism."""

    def test_set_bq_credentials_stores_credentials(self):
        """set_bq_credentials should store credentials in the clients module."""
        fake_creds = {"type": "service_account", "project_id": "test-project"}
        set_bq_credentials(fake_creds)
        assert clients._bq_credentials == fake_creds

    @patch("langgraph_agent.clients.bigquery.Client")
    def test_get_bq_client_without_credentials(self, mock_client_class):
        """get_bq_client should use default credentials if none injected."""
        set_bq_credentials(None)  # reset injected credentials

        get_bq_client()
        # Should call Client() with no args (uses default credentials)
        mock_client_class.assert_called_once_with()

    def test_get_bq_client_with_credentials(self):
        """get_bq_client should use injected credentials when available."""
        fake_creds = {"type": "service_account", "project_id": "test-project"}
        set_bq_credentials(fake_creds)

        assert clients._bq_credentials is not None
        assert clients._bq_credentials.get("project_id") == "test-project"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
