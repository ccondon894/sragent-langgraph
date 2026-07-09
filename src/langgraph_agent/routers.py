from langgraph_agent.state import SRAQueryState
from langgraph_agent.logging_utils import log_router, logger
from typing import Literal

def check_slots(state: SRAQueryState) -> str:
    """Router for checking if all required info has been filled."""
    organism = state.get("organism")
    library_source = state.get("library_source")

    if organism is not None and library_source is not None:
        decision = "ready_to_query"
    else:
        decision = "missing_info"

    # DEBUG: Log routing decision
    log_router("check_slots", decision,
               organism=organism,
               library_source=library_source)

    return decision

def check_execution(state: SRAQueryState) -> Literal["success", "zero_results", "sql_error", "max_retries"]:
    """
    Determines the next step based on the execution output.
    """

    error = state.get("error_message")
    results = state.get("query_results")
    retry_count = state.get("retry_count", 0)

    # Determine result type for logging
    results_type = type(results).__name__
    results_len = len(results) if results is not None else "N/A"

    # Check if we've hit max retries (max 3 attempts)
    if error and retry_count >= 3:
        decision = "max_retries"
        log_router("check_execution", decision,
                   error=bool(error),
                   error_preview=str(error)[:50] if error else None,
                   results_type=results_type,
                   results_len=results_len,
                   retry_count=retry_count)
        return decision

    if error:
        decision = "sql_error"
        log_router("check_execution", decision,
                   error=bool(error),
                   error_preview=str(error)[:50] if error else None,
                   results_type=results_type,
                   results_len=results_len,
                   retry_count=retry_count)
        return decision

    # if results list empty, criteria was too strict
    if results is not None and len(results) == 0:
        decision = "zero_results"
        log_router("check_execution", decision,
                   error=bool(error),
                   results_type=results_type,
                   results_len=results_len,
                   retry_count=retry_count)
        return decision

    if results and len(results) > 0:
        decision = "success"
        log_router("check_execution", decision,
                   error=bool(error),
                   results_type=results_type,
                   results_len=results_len,
                   retry_count=retry_count)
        return decision

    # Catch-all: unexpected state (e.g., error=None and results=None)
    # This can happen if bq_executor fails in an unexpected way
    logger.warning(f"check_execution: UNEXPECTED STATE - error={error}, results_type={results_type}, retry_count={retry_count}")
    log_router("check_execution", "sql_error (catch-all)",
               error=bool(error),
               results_type=results_type,
               results_len=results_len,
               retry_count=retry_count)
    # Treat as sql_error to trigger retry logic (Milestone 13 fix)
    return "sql_error"
