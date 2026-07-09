from langgraph_agent.state import SRAQueryState
from langgraph_agent.config import MANDATORY_FIELDS, DEFAULT_COLUMNS
from langgraph_agent.logging_utils import log_node, logger
from langgraph_agent.validators import resolve_library_source, resolve_platform
from langgraph_agent.prompts import param_extractor_prompt, clarifier_prompt, error_synthesis_prompt, synthesis_prompt
from langgraph_agent.clients import get_bq_client, get_valid_columns
from langgraph_agent.prompts import SQL_SYSTEM_PROMPT
from typing import Dict, Any
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from google.cloud import bigquery
import json
import time


# param extractor node
def param_extractor(state: SRAQueryState, structured_llm) -> Dict[str, Any]:

    if isinstance(state["messages"][-1].content, str):
        latest_message: str = state["messages"][-1].content

    # 1. Get the OLD data (Saved State)
    old_organism = state.get("organism")
    old_source = state.get("library_source")
    old_platform = state.get("platform")
    old_keywords = state.get("keywords") or []

    # DEBUG: Log node entry
    log_node("param_extractor", "entry",
             organism=old_organism,
             library_source=old_source,
             platform=old_platform,
             keywords=old_keywords,
             msg_preview=latest_message[:50] if latest_message else None)

    # 1.5 PRE-LLM: Simple string matching for clarification responses
    # This catches cases where the user just replies "transcriptomic",
    # "RNA seq", "oxford nanopore", etc. Uses the same separator-tolerant
    # resolvers as the Pydantic validators so both paths behave identically.
    pre_matched_source = resolve_library_source(latest_message)
    pre_matched_platform = resolve_platform(latest_message)

    if pre_matched_source:
        logger.debug("Pre-LLM match: library_source = %s", pre_matched_source)
    if pre_matched_platform:
        logger.debug("Pre-LLM match: platform = %s", pre_matched_platform)

    # 2. Get the NEW data (LLM Extraction)
    # We pass the old state to the prompt so the LLM knows context,
    # but we still need to handle the merge logic ourselves.
    current_params = {
        "organism": old_organism,
        "library_source": old_source,
        "platform": old_platform,
        "keywords": old_keywords
    }

    extracted_data = (param_extractor_prompt | structured_llm).invoke({
        "input": latest_message,
        "existing_state_json": json.dumps(current_params),
        "user_input": latest_message
    })

    new_data = extracted_data.model_dump()

    # 3. The Manual "Save" Logic (Use new if exists, otherwise keep old)
    # Priority: LLM extraction > Pre-LLM match > Old value
    # This ensures we never overwrite a value with None

    final_organism = new_data['organism'] if new_data['organism'] else old_organism

    # For library_source: LLM > pre-match > old
    if new_data['library_source']:
        final_source = new_data['library_source']
    elif pre_matched_source:
        final_source = pre_matched_source
    else:
        final_source = old_source

    # For platform: LLM > pre-match > old
    if new_data['platform']:
        final_platform = new_data['platform']
    elif pre_matched_platform:
        final_platform = pre_matched_platform
    else:
        final_platform = old_platform

    # For keywords, we might want to add to the list, not replace
    new_keywords = new_data.get('keywords')
    if new_keywords:
        final_keywords = list(set(old_keywords + new_keywords))
    else:
        final_keywords = old_keywords

    # 4. Return the fully reconstructed state
    result = {
        "organism": final_organism,
        "library_source": final_source,
        "platform": final_platform,
        "keywords": final_keywords
    }

    # DEBUG: Log node exit
    log_node("param_extractor", "exit",
             organism=final_organism,
             library_source=final_source,
             platform=final_platform,
             keywords=final_keywords,
             pre_matched_source=pre_matched_source,
             llm_extracted_source=new_data.get('library_source'))

    return result


def clarifier(state: SRAQueryState, llm) -> Dict[str, Any]:
    """The clarifier node. """
    clarifier_chain = clarifier_prompt | llm

    # Identify all fields that are currently None
    missing_fields = [field for field in MANDATORY_FIELDS if state.get(field) is None]

    # DEBUG: Log node entry
    log_node("clarifier", "entry",
             organism=state.get("organism"),
             library_source=state.get("library_source"),
             missing_fields=missing_fields)

    # Generate the clarification question using the missing fields string
    missing_fields_str = ','.join(missing_fields)
    clarification_text = clarifier_chain.invoke({
        "missing_fields": missing_fields_str
    }).content

    # Format results as an AIMessage
    clarification_message = AIMessage(content=clarification_text)

    # DEBUG: Log node exit
    log_node("clarifier", "exit",
             missing_fields=missing_fields,
             clarification_preview=clarification_text[:60] if clarification_text else None)

    return {"messages": [clarification_message]}


def sql_compiler(state: SRAQueryState, structured_sql_llm) -> Dict[str, Any]:

    # Get current retry count BEFORE incrementing
    current_retry = state.get("retry_count", 0)

    # DEBUG: Log node entry
    log_node("sql_compiler", "entry",
             retry_count=current_retry,
             organism=state.get("organism"),
             library_source=state.get("library_source"),
             platform=state.get("platform"),
             keywords=state.get("keywords"),
             has_error=bool(state.get("error_message")))

    # Prepare context
    error_msg = state.get("error_message") or ""
    error_context = f"The previous query failed: {error_msg}" if error_msg else "No previous errors"

    # Prepare parameters for prompt (convert None to empty string)
    params = {
        "organism": state.get("organism") or "",
        "source": state.get("library_source") or "",
        "platform": state.get("platform") or "",
        "keywords": ", ".join(state.get("keywords") or []),
        "error_context": error_context
    }

    # Invoke LLM to generate WHERE clause and column selection
    sql_chain = PromptTemplate.from_template(SQL_SYSTEM_PROMPT) | structured_sql_llm
    components = sql_chain.invoke(params)

    where_clause = components.where_clause.strip()

    # Validate columns against actual BigQuery schema
    requested = set(components.columns)
    valid = get_valid_columns()
    safe_columns = [c for c in components.columns if c in valid]

    # Log dropped columns for debugging
    dropped = requested - set(safe_columns)
    if dropped:
        logger.debug("Dropped invalid columns: %s", dropped)

    # Fall back to defaults if all columns were invalid
    if not safe_columns:
        safe_columns = DEFAULT_COLUMNS
        logger.debug("All requested columns invalid, using defaults: %s", DEFAULT_COLUMNS)

    # Build both queries programmatically
    col_str = ", ".join(safe_columns)

    count_sql = f"""
    SELECT COUNT(*) as total
    FROM `nih-sra-datastore.sra.metadata`
    WHERE {where_clause if where_clause else '1=1'}
    """

    sample_sql = f"""
    SELECT {col_str}
    FROM `nih-sra-datastore.sra.metadata`
    WHERE {where_clause if where_clause else '1=1'}
    LIMIT 100
    """

    # Log the generated SQL for debugging
    logger.debug("WHERE clause: %s", where_clause if where_clause else "(empty - will use 1=1)")
    logger.debug("Full COUNT SQL:\n%s", count_sql.strip())
    logger.debug("Full SAMPLE SQL:\n%s", sample_sql.strip())

    # Increment retry count and reset error message
    retry_count = state.get("retry_count", 0) + 1

    # DEBUG: Log node exit
    log_node("sql_compiler", "exit",
             retry_count=retry_count,
             where_clause_preview=where_clause[:80] if where_clause else "(empty)",
             columns=safe_columns)

    return {
        "count_sql": count_sql.strip(),
        "generated_sql": sample_sql.strip(),
        "error_message": None,
        "retry_count": retry_count
    }


def bq_executor(state: SRAQueryState) -> Dict[str, Any]:
    """ The executor node. """
    # DEBUG: Log node entry
    log_node("bq_executor", "entry",
                retry_count=state.get("retry_count", 0),
                has_count_sql=bool(state.get("count_sql")),
                has_sample_sql=bool(state.get("generated_sql")))

    start_time = time.time()

    try:
        # Initialize BigQuery client (uses injected credentials or environment)
        client = get_bq_client()

        total_count = None

        # Stage 1: Run count query if available (cheap, no column scan)
        count_sql = state.get('count_sql')
        if count_sql:

            count_job = client.query(count_sql)
            count_result = list(count_job.result())
            if count_result:
                total_count = count_result[0]["total"]
            logger.info("Found %s total matching records", f"{total_count:,}" if total_count is not None else "0")

        # Stage 2: Run sample query (limited to 100 rows)
        sample_sql = state['generated_sql']
        

        # Configure query job with reduced billing limit for samples
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=5 * 10**9  # 5 GB cap for sample queries
        )

        # Execute sample query
        query_job = client.query(sample_sql, job_config=job_config)

        # Convert results to list of dictionaries
        results = [dict(row) for row in query_job.result()]
        logger.info("Retrieved %d sample records", len(results))

        elapsed = time.time() - start_time

        # DEBUG: Log node exit (success)
        log_node("bq_executor", "exit",
                    status="SUCCESS",
                    elapsed_sec=f"{elapsed:.2f}",
                    total_count=total_count,
                    result_count=len(results))

        return {
            "query_results": results,
            "total_count": total_count,
            "error_message": None
        }

    except Exception as e:
        # Capture BigQuery errors (invalid schema, syntax, auth, etc.)
        error_msg = str(e)
        elapsed = time.time() - start_time

        # DEBUG: Log node exit (error)
        log_node("bq_executor", "exit",
                    status="ERROR",
                    elapsed_sec=f"{elapsed:.2f}",
                    error_preview=error_msg[:100] if error_msg else None)

        # Explicitly set query_results to None to prevent check_execution from hitting unexpected state
        return {"error_message": error_msg, "query_results": None}


def response_synthesizer(state: SRAQueryState, llm) -> Dict[str, Any]:
    """Node to synthesize conversational response for all query outcomes."""
    results = state.get("query_results")  # None means no query was run, [] means empty results
    error = state.get("error_message")
    retry_count = state.get("retry_count", 0)
    total_count = state.get("total_count")

    # Determine result type for logging
    results_type = type(results).__name__
    results_len = len(results) if results is not None else "N/A"

    # DEBUG: Log node entry
    log_node("response_synthesizer", "entry",
             error=bool(error),
             results_type=results_type,
             results_len=results_len,
             retry_count=retry_count,
             total_count=total_count)

    # Build search description with only non-empty values
    search_parts = []
    organism = state.get("organism")
    source = state.get("library_source")
    keywords_list = state.get("keywords") or []

    if organism:
        search_parts.append(f"organism: {organism}")
    if source:
        search_parts.append(f"library source: {source}")
    if keywords_list:
        search_parts.append(f"keywords: {', '.join(keywords_list)}")

    search_description = "; ".join(search_parts) if search_parts else "no specific criteria"

    branch = None  # Track which branch we take

    try:
        if error and retry_count >= 3:
            branch = "max_retries_error"
            # Max retries exceeded
            summary = (
                error_synthesis_prompt | llm | StrOutputParser()
            ).invoke({
                "error": error,
                "search": search_description
            })
            message = f"Unfortunately, the query couldn't be fixed after {retry_count} attempts.\n\n{summary}"

        elif error:
            branch = "error_not_max_retries"
            # Error but not max retries (shouldn't happen with current routing)
            summary = (
                error_synthesis_prompt | llm | StrOutputParser()
            ).invoke({
                "error": error,
                "search": search_description
            })
            message = summary

        elif results is None:
            branch = "no_query_ran_from_clarifier"
            # No query was run (came from clarifier) - don't add another message
            # The clarifier already added a clarification question to messages
            log_node("response_synthesizer", "exit",
                     branch=branch,
                     returning="empty_dict")
            return {}

        elif len(results) == 0:
            branch = "zero_results"
            # Query ran but no results found
            summary = (
                error_synthesis_prompt | llm | StrOutputParser()
            ).invoke({
                "error": "No datasets matched the search criteria.",
                "search": search_description
            })
            message = summary

        else:
            # Success - check if result set is very large and suggest narrowing
            if total_count and total_count > 10000:
                branch = "success_large_dataset"
                message = (
                    f"Found {total_count:,} datasets matching your search. "
                    f"That's a lot of data! Here's a sample of {len(results)} datasets to preview.\n\n"
                    f"Consider narrowing your search by:\n"
                    f"- **Platform** (e.g., 'only Illumina', 'Oxford Nanopore')\n"
                    f"- **Time range** (e.g., 'from the last 2 years')\n"
                    f"- **Tissue/Sample type** (e.g., 'brain tissue', 'blood samples')\n"
                    f"- **Project/BioProject ID** (e.g., 'PRJNA123456')\n\n"
                    f"Here are {len(results)} samples to get started:\n\n"
                )
                sample_results = json.dumps(results[:5], indent=2)
                message += sample_results
            else:
                branch = "success_normal"
                # Standard summary for normal-sized result sets
                sample_results = json.dumps(results[:10], indent=2)
                total_str = f"{total_count:,} total, showing {len(results)}" if total_count else f"{len(results)}"
                summary = (
                    synthesis_prompt | llm | StrOutputParser()
                ).invoke({
                    "search": search_description,
                    "count": total_str,
                    "sample": sample_results
                })
                message = summary

    except Exception as e:
        branch = "exception"
        message = f"Error generating summary: {str(e)}"

    # DEBUG: Log node exit
    log_node("response_synthesizer", "exit",
             branch=branch,
             message_len=len(message) if message else 0)

    return {"messages": [AIMessage(content=message)]}