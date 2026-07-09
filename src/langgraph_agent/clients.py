from typing import Dict, Any
from google.cloud import bigquery
from langgraph_agent.config import DEFAULT_COLUMNS
from langgraph_agent.logging_utils import logger
import time
_bq_credentials = None
_gcp_project = None

def set_bq_credentials(credentials_dict: Dict[str, Any]) -> None:
    """
    Add BigQuery and Google AI service accont credentials for use. 
    """
    global _bq_credentials, _gcp_project
    _bq_credentials = credentials_dict
    if credentials_dict:
        _gcp_project = credentials_dict.get("project_id")

def get_bq_client() -> bigquery.Client:
    """
    Get a BigQuery client using injected credentials if available,
    otherwise use default credentials from environment.

    Returns:
        google.cloud.bigquery.Client instance
    """
    if _bq_credentials:
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_info(
            _bq_credentials,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return bigquery.Client(credentials=creds, project=_bq_credentials.get("project_id"))
    else:
        return bigquery.Client()

# Schema cache with TTL
_schema_cache = {"columns": None, "fetched_at": 0}
SCHEMA_TTL = 86400  # 24 hours

def get_valid_columns() -> set:
    """
    Fetch valid column names from BigQuery schema with caching.
    Uses 24-hour TTL to allow schema updates without restarting.
    """
    now = time.time()
    if _schema_cache["columns"] and (now - _schema_cache["fetched_at"]) < SCHEMA_TTL:
        return _schema_cache["columns"]
    try:
        client = get_bq_client()
        table = client.get_table("nih-sra-datastore.sra.metadata")
        columns = {f.name for f in table.schema}
        _schema_cache["columns"] = columns
        _schema_cache["fetched_at"] = now
        return columns
    except Exception as e:
        logger.warning("Schema fetch failed (%s); falling back to default columns", e)
        # Serve stale cache if we have it, else the minimal safe set.
        return _schema_cache["columns"] or set(DEFAULT_COLUMNS)

