"""
Fake BigQuery client for testing without making real database queries.

This module provides mock objects that mimic BigQuery's API:
- Mock Client for creating queries
- Mock QueryJob for executing queries
- Mock RowIterator for iterating results
- Mock Table and Schema for schema validation
"""

from typing import Any, Dict, List, Optional
from unittest.mock import Mock, MagicMock


class FakeSchemaField:
    """Mock BigQuery schema field."""

    def __init__(self, name: str, field_type: str = "STRING"):
        self.name = name
        self.field_type = field_type


class FakeTableSchema:
    """Mock BigQuery table schema."""

    def __init__(self, columns: List[str]):
        """
        Initialize fake schema.

        Args:
            columns: List of column names
        """
        self.columns = columns
        self._schema_fields = [FakeSchemaField(col, "STRING") for col in columns]

    @property
    def schema(self) -> List[FakeSchemaField]:
        """Return schema fields."""
        return self._schema_fields


class FakeQueryResult:
    """Mock result from a BigQuery query."""

    def __init__(self, rows: List[Dict[str, Any]]):
        """
        Initialize fake query result.

        Args:
            rows: List of result rows as dictionaries
        """
        self.rows = rows
        self._index = 0

    def __iter__(self):
        """Iterate over rows."""
        return iter(self.rows)

    def __len__(self):
        """Return number of rows."""
        return len(self.rows)

    def to_dataframe(self):
        """Convert to pandas DataFrame (mock)."""
        try:
            import pandas as pd
            return pd.DataFrame(self.rows)
        except ImportError:
            return None


class FakeQueryJob:
    """Mock BigQuery QueryJob."""

    def __init__(self, query: str, result_rows: Optional[List[Dict[str, Any]]] = None):
        """
        Initialize fake query job.

        Args:
            query: SQL query string
            result_rows: List of result rows to return
        """
        self.query = query
        self.result_rows = result_rows or []
        self._result = FakeQueryResult(self.result_rows)

    def result(self, max_results: Optional[int] = None) -> FakeQueryResult:
        """Return query results."""
        if max_results:
            return FakeQueryResult(self.result_rows[:max_results])
        return self._result

    @property
    def total_bytes_processed(self) -> int:
        """Return estimated bytes processed."""
        # Rough estimate: 1KB per row
        return len(self.result_rows) * 1024

    @property
    def total_bytes_billed(self) -> int:
        """Return bytes billed (BigQuery minimum is 1MB)."""
        return max(1024 * 1024, self.total_bytes_processed)  # Minimum 1MB


class FakeClient:
    """Mock BigQuery Client."""

    # Query cost tracking (BigQuery costs ~$6.25 per TB)
    COST_PER_BYTE = 6.25 / (1024 ** 4)  # $6.25 per TB

    def __init__(self, project: str = "test-project", **kwargs):
        """
        Initialize fake BigQuery client.

        Args:
            project: GCP project ID
        """
        self.project = project
        self.credentials = kwargs.get("credentials")
        self._tables = {
            "nih-sra-datastore.sra.metadata": FakeTableSchema([
                "acc",
                "organism",
                "librarysource",
                "libraryselection",
                "librarylayout",
                "platform",
                "mbases",
                "releasedate",
                "center_name",
                "sra_study",
                "bioproject",
                "sample_name",
                "library_name",
                "attributes"
            ])
        }
        self.total_bytes_processed = 0
        self.total_cost_usd = 0.0

    def get_table(self, table_id: str):
        """Get table schema."""
        if table_id in self._tables:
            return self._tables[table_id]
        raise ValueError(f"Table {table_id} not found in mock client")

    def query(self, query: str, **kwargs) -> FakeQueryJob:
        """
        Execute a query and return mock results.

        Args:
            query: SQL query string
            **kwargs: Additional BigQuery query parameters

        Returns:
            FakeQueryJob with mock results
        """
        # Generate mock results based on query type
        result_rows = self._generate_mock_results(query)

        # Track cost
        job = FakeQueryJob(query, result_rows)
        self.total_bytes_processed += job.total_bytes_processed
        self.total_cost_usd += job.total_bytes_billed * self.COST_PER_BYTE

        return job

    def _generate_mock_results(self, query: str) -> List[Dict[str, Any]]:
        """Generate mock results based on query content."""
        query_lower = query.lower()

        # COUNT queries return a single row
        if "count(*)" in query_lower:
            return [{"total": 42}]

        # Regular select queries return sample records
        return [
            {
                "acc": "SRR123456",
                "organism": "Homo sapiens",
                "librarysource": "TRANSCRIPTOMIC",
                "platform": "ILLUMINA",
                "center_name": "Cancer Research Center",
                "mbases": 5000,
            },
            {
                "acc": "SRR123457",
                "organism": "Homo sapiens",
                "librarysource": "TRANSCRIPTOMIC",
                "platform": "ILLUMINA",
                "center_name": "Lung Institute",
                "mbases": 3000,
            },
            {
                "acc": "SRR123458",
                "organism": "Homo sapiens",
                "librarysource": "TRANSCRIPTOMIC",
                "platform": "ILLUMINA",
                "center_name": "Cancer Biology Lab",
                "mbases": 7500,
            },
        ]

    @classmethod
    def reset_cost_tracking(cls):
        """Reset global cost tracking."""
        pass  # Instance-based tracking

    def get_total_cost(self) -> float:
        """Get estimated total BigQuery cost."""
        return self.total_cost_usd

    def get_bytes_processed(self) -> int:
        """Get total bytes processed."""
        return self.total_bytes_processed
