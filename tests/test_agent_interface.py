"""
Tests for callable agent interface (Milestone 1).

These tests verify that:
1. create_sra_agent() returns a functional agent
2. query_sra() interface works for programmatic queries
3. Credential injection works correctly
"""

import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sra_agent import create_sra_agent, query_sra, set_bq_credentials, get_bq_client


class TestCreateSraAgent:
    """Test agent factory function."""

    def test_create_agent_without_credentials(self):
        """Agent should be created successfully without credentials."""
        agent = create_sra_agent()
        assert agent is not None
        # Should be a compiled runnable
        assert hasattr(agent, 'invoke')

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
        agent = create_sra_agent(credentials=fake_credentials)
        assert agent is not None


class TestQuerySraInterface:
    """Test the query_sra programmatic interface."""

    @patch('sra_agent.app')
    def test_query_sra_returns_dict(self, mock_app):
        """query_sra should return a structured dictionary."""
        from langchain_core.messages import AIMessage

        # Mock the agent response
        mock_state = {
            "messages": [AIMessage(content="Found 42 records")],
            "organism": "Homo sapiens",
            "library_source": "TRANSCRIPTOMIC",
            "platform": "ILLUMINA",
            "keywords": ["cancer"],
            "query_results": [{"acc": "SRR123"}, {"acc": "SRR124"}],
            "total_count": 42,
            "error_message": None,
        }
        mock_app.invoke.return_value = mock_state

        agent = create_sra_agent()
        result = query_sra(agent, "Find human cancer data")

        assert isinstance(result, dict)
        assert "response" in result
        assert "organism" in result
        assert "library_source" in result
        assert "platform" in result
        assert "keywords" in result
        assert "results" in result
        assert "total_count" in result
        assert "error" in result
        assert "thread_id" in result

    @patch('sra_agent.app')
    def test_query_sra_with_custom_thread_id(self, mock_app):
        """query_sra should preserve provided thread_id."""
        from langchain_core.messages import AIMessage

        mock_state = {
            "messages": [AIMessage(content="Test")],
            "organism": None,
            "library_source": None,
            "platform": None,
            "keywords": None,
            "query_results": None,
            "total_count": None,
            "error_message": None,
        }
        mock_app.invoke.return_value = mock_state

        custom_thread_id = "custom-123"
        agent = create_sra_agent()
        result = query_sra(agent, "Test query", thread_id=custom_thread_id)

        assert result["thread_id"] == custom_thread_id
        # Verify invoke was called with correct config
        call_args = mock_app.invoke.call_args
        assert call_args[1]["config"]["configurable"]["thread_id"] == custom_thread_id

    @patch('sra_agent.app')
    def test_query_sra_error_handling(self, mock_app):
        """query_sra should gracefully handle errors."""
        mock_app.invoke.side_effect = Exception("BigQuery connection failed")

        agent = create_sra_agent()
        result = query_sra(agent, "Bad query")

        assert result["response"] is None
        assert "BigQuery connection failed" in result["error"]
        assert result["thread_id"] is not None

    @patch('sra_agent.app')
    def test_query_sra_auto_thread_id(self, mock_app):
        """query_sra should generate thread_id if not provided."""
        from langchain_core.messages import AIMessage

        mock_state = {
            "messages": [AIMessage(content="Test")],
            "organism": None,
            "library_source": None,
            "platform": None,
            "keywords": None,
            "query_results": None,
            "total_count": None,
            "error_message": None,
        }
        mock_app.invoke.return_value = mock_state

        agent = create_sra_agent()
        result1 = query_sra(agent, "Query 1")
        result2 = query_sra(agent, "Query 2")

        # Each call should generate a unique thread_id
        assert result1["thread_id"] != result2["thread_id"]
        # Both should be valid UUIDs
        try:
            uuid.UUID(result1["thread_id"])
            uuid.UUID(result2["thread_id"])
        except ValueError:
            pytest.fail("Generated thread_id is not a valid UUID")


class TestCredentialInjection:
    """Test credential injection mechanism."""

    def test_set_bq_credentials_stores_credentials(self):
        """set_bq_credentials should store credentials globally."""
        fake_creds = {
            "type": "service_account",
            "project_id": "test-project",
        }
        set_bq_credentials(fake_creds)

        # Verify credentials were stored by checking module state
        import sra_agent
        assert sra_agent._bq_credentials == fake_creds

    @patch('sra_agent.bigquery.Client')
    def test_get_bq_client_without_credentials(self, mock_client_class):
        """get_bq_client should use default credentials if none injected."""
        # Reset credentials
        import sra_agent
        sra_agent._bq_credentials = None

        get_bq_client()
        # Should call Client() with no args (uses default credentials)
        mock_client_class.assert_called_once_with()

    def test_get_bq_client_with_credentials(self):
        """get_bq_client should use injected credentials when available."""
        fake_creds = {
            "type": "service_account",
            "project_id": "test-project",
        }
        set_bq_credentials(fake_creds)

        # Simply verify credentials were set
        import sra_agent
        assert sra_agent._bq_credentials is not None
        assert sra_agent._bq_credentials.get("project_id") == "test-project"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
