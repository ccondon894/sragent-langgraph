from typing import List, Optional, TypedDict, Annotated, Dict, Any, Literal
import operator
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import uuid
from pydantic import BaseModel, Field, field_validator
import json
from google.cloud import bigquery
from dotenv import load_dotenv
from datetime import datetime
import time

load_dotenv()

# ============================================================================
# Credential Management for Programmatic Access
# ============================================================================
# Global credential storage for BigQuery client injection
_bq_credentials = None

def set_bq_credentials(credentials_dict: Dict[str, Any]) -> None:
    """
    Inject BigQuery service account credentials for programmatic use.

    Args:
        credentials_dict: Service account JSON as dictionary
                         (from google.oauth2.service_account.Credentials.from_service_account_info)
    """
    global _bq_credentials
    _bq_credentials = credentials_dict

def get_bq_client() -> bigquery.Client:
    """
    Get a BigQuery client using injected credentials if available,
    otherwise use default credentials from environment.

    Returns:
        google.cloud.bigquery.Client instance
    """
    if _bq_credentials:
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_info(_bq_credentials)
        return bigquery.Client(credentials=creds, project=_bq_credentials.get("project_id"))
    else:
        return bigquery.Client()

# ============================================================================
# Schema Validation Infrastructure
# ============================================================================
# Fallback columns in case BigQuery schema fetch fails
FALLBACK_COLUMNS = {"acc", "organism", "librarysource", "platform", "mbases"}
DEFAULT_COLUMNS = ["acc", "organism", "librarysource", "platform", "mbases"]

# Schema cache with TTL
_schema_cache = {"columns": None, "fetched_at": 0}
SCHEMA_TTL = 86400  # 24 hours

def get_valid_columns() -> set:
    """
    Fetch valid column names from BigQuery schema with caching.
    Uses 24-hour TTL to allow schema updates without restarting.
    Falls back to hardcoded list if fetch fails.
    """
    now = time.time()

    # Return cached columns if still fresh
    if _schema_cache["columns"] and (now - _schema_cache["fetched_at"]) < SCHEMA_TTL:
        return _schema_cache["columns"]

    try:
        # Fetch schema from BigQuery
        client = get_bq_client()
        table = client.get_table("nih-sra-datastore.sra.metadata")
        columns = {f.name for f in table.schema}

        # Update cache
        _schema_cache["columns"] = columns
        _schema_cache["fetched_at"] = now
        print(f"   Schema fetched: {len(columns)} columns available")
        return columns

    except Exception as e:
        print(f"   Schema fetch failed: {e}")
        # Return cached columns if available, otherwise fall back
        if _schema_cache["columns"]:
            return _schema_cache["columns"]
        return FALLBACK_COLUMNS


class SRAQueryState(TypedDict):

    #1. annotate messages
    messages: Annotated[List[BaseMessage], operator.add]

    #2. The SRA Form. Extracted SRA parameters
    organism: Optional[str]
    library_source: Optional[str]  # e.g., 'TRANSCRIPTOMIC', 'METAGENOMIC'
    platform: Optional[str]          # e.g., 'ILLUMINA', 'OXFORD_NANOPORE'
    keywords: Optional[List[str]]    # e.g., ['cancer', 'lung']

    #3. Execution Artifacts
    count_sql: Optional[str]         # COUNT query (returns total matching records)
    generated_sql: Optional[str]     # Sample query (LIMIT 100)
    query_results: Optional[List[dict]] # The rows returned from BigQuery
    total_count: Optional[int]       # Total matching records from count query
    error_message: Optional[str]     # If BigQuery fails

    # 4. Control Flags
    retry_count: int  # Track SQL regeneration attempts to prevent infinite loops

# ============================================================================
# Field Validation Constants
# ============================================================================
# Valid library source values from BigQuery
VALID_LIBRARY_SOURCES = {
    "TRANSCRIPTOMIC", "GENOMIC", "METAGENOMIC",
    "TRANSCRIPTOMIC SINGLE CELL", "GENOMIC SINGLE CELL",
    "VIRAL RNA", "SYNTHETIC", "OTHER", "METATRANSCRIPTOMIC"
}

# Common aliases for library sources
LIBRARY_SOURCE_ALIASES = {
    "RNA-SEQ": "TRANSCRIPTOMIC",
    "RNA-SEQUENCING": "TRANSCRIPTOMIC",
    "MRNA": "TRANSCRIPTOMIC",
    "WGS": "GENOMIC",
    "WHOLE GENOME": "GENOMIC",
    "DNA": "GENOMIC",
    "WXS": "GENOMIC",  # Exome is genomic DNA
    "EXOME": "GENOMIC",
    "METAGENOME": "METAGENOMIC",
    "ENVIRONMENTAL": "METAGENOMIC",
}

# Valid platform values
VALID_PLATFORMS = {
    "ILLUMINA", "OXFORD_NANOPORE", "PACBIO_SMRT",
    "ION_TORRENT", "BGISEQ", "DNBSEQ", "HELICOS"
}

# Common platform aliases
PLATFORM_ALIASES = {
    "PACBIO": "PACBIO_SMRT",
    "PB": "PACBIO_SMRT",
    "ONT": "OXFORD_NANOPORE",
    "NANOPORE": "OXFORD_NANOPORE",
}

# Common organism name aliases
ORGANISM_ALIASES = {
    "HUMAN": "Homo sapiens",
    "HOMO SAPIENS": "Homo sapiens",
    "MOUSE": "Mus musculus",
    "MUS MUSCULUS": "Mus musculus",
    "RAT": "Rattus norvegicus",
    "FLY": "Drosophila melanogaster",
    "WORM": "Caenorhabditis elegans",
    "ZEBRAFISH": "Danio rerio",
    "YEAST": "Saccharomyces cerevisiae",
    "ARABIDOPSIS": "Arabidopsis thaliana",
}

# This will be what our param_extractor returns.
# This is like a subset of our SRAQueryState.
class SRAExtraction(BaseModel):
    """
    Schema for extracting SRA query parameters from user input.
    """
    organism: Optional[str] = Field(
        None, description="The species, e.g., 'Homo sapiens' or 'Mus musculus'."
    )
    library_source: Optional[str] = Field(
        None, description="The library source type, e.g., 'TRANSCRIPTOMIC', 'METAGENOMIC', 'GENOMIC'."
    )
    platform: Optional[str] = Field(
        None, description="The sequencing platform, e.g., 'ILLUMINA', 'OXFORD_NANOPORE'."
    )
    keywords: Optional[List[str]] = Field(
        None, description="A list of relevant search keywords, e.g., ['cancer', 'lung', 'metagenomics']."
    )

    @field_validator('organism')
    @classmethod
    def validate_organism(cls, v):
        """Standardize common organism names to scientific names."""
        if v is None:
            return v

        v_upper = v.upper()

        # Check if it's an alias
        if v_upper in ORGANISM_ALIASES:
            return ORGANISM_ALIASES[v_upper]

        # Return as-is (organism names are too varied to enumerate completely)
        return v

    @field_validator('library_source')
    @classmethod
    def validate_library_source(cls, v):
        """Validate and normalize library source values."""
        if v is None:
            return v

        v_upper = v.upper()

        # Direct match
        if v_upper in VALID_LIBRARY_SOURCES:
            return v_upper

        # Check aliases
        if v_upper in LIBRARY_SOURCE_ALIASES:
            return LIBRARY_SOURCE_ALIASES[v_upper]

        # Return None on mismatch - triggers clarifier to ask user
        print(f"   Warning: Unknown library source '{v}' - will ask for clarification")
        return None

    @field_validator('platform')
    @classmethod
    def validate_platform(cls, v):
        """Validate and normalize platform values."""
        if v is None:
            return v

        v_upper = v.upper()

        # Direct match
        if v_upper in VALID_PLATFORMS:
            return v_upper

        # Check aliases
        if v_upper in PLATFORM_ALIASES:
            return PLATFORM_ALIASES[v_upper]

        # Return None on mismatch - triggers clarifier to ask user
        print(f"   Warning: Unknown platform '{v}' - will ask for clarification")
        return None

# Schema for SQL component generation
class SQLComponents(BaseModel):
    """
    Structured output for SQL WHERE clause and column selection.
    The sql_compiler function will use these to construct both COUNT and SAMPLE queries.
    """
    where_clause: str = Field(
        description="The WHERE clause conditions (without WHERE keyword). "
        "Use AND for multiple conditions. Return empty string if no filters needed."
    )
    columns: List[str] = Field(
        default=DEFAULT_COLUMNS,
        description="Columns to SELECT. Will be validated against actual schema."
    )

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
structured_llm = llm.with_structured_output(SRAExtraction)
structured_sql_llm = llm.with_structured_output(SQLComponents)

### NODES ###

# 1. param_extractor node

param_extractor_prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
         "You are an expert SRA Metadata extractor.\n "
         "Your goal is to fill the following JSON schema: {{organism, library_source, platform, keywords}}.\n"
         "Current State: {existing_state_json} Latest User Input: {user_input}\n"
         "INSTRUCTIONS:\n"
         "1. Update the Current State with information from the Latest User Input.\n"
         "2. Organism mapping:\n"
         "   - 'Human' → 'Homo sapiens'\n"
         "   - 'Mouse' → 'Mus musculus'\n"
         "   - Otherwise return the species name as-is\n"
         "3. Library Source mapping (use UPPERCASE):\n"
         "   - 'RNA-seq', 'transcriptomic', 'mRNA' → 'TRANSCRIPTOMIC'\n"
         "   - 'WGS', 'genome', 'genomic' → 'GENOMIC'\n"
         "   - 'metagenome', 'environmental' → 'METAGENOMIC'\n"
         "   - 'single cell' with transcriptomic → 'TRANSCRIPTOMIC SINGLE CELL'\n"
         "   - 'single cell' with genomic → 'GENOMIC SINGLE CELL'\n"
         "4. Platform values (UPPERCASE): ILLUMINA, OXFORD_NANOPORE, PACBIO, ION_TORRENT, HELICOS\n"
         "5. Keywords: Extract any biological terms (tissues, diseases, sample types)\n"
         "6. Return the merged JSON."),
         ("human", "{input}")
    ]
)

def param_extractor(state: SRAQueryState) -> Dict[str, Any]:

    latest_message = state["messages"][-1].content

    # 1. Get the OLD data (Saved State)
    old_organism = state.get("organism")
    old_source = state.get("library_source")
    old_platform = state.get("platform")
    old_keywords = state.get("keywords") or []

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
    # This ensures we never overwrite a value with None

    final_organism = new_data['organism'] if new_data['organism'] else old_organism
    final_source = new_data['library_source'] if new_data['library_source'] else old_source
    final_platform = new_data['platform'] if new_data['platform'] else old_platform
    
    # For keywords, we might want to add to the list, not replace
    new_keywords = new_data.get('keywords')
    if new_keywords:
        final_keywords = list(set(old_keywords + new_keywords))
    else:
        final_keywords = old_keywords

    # 4. Return the fully reconstructed state
    return {
        "organism": final_organism,
        "library_source": final_source,
        "platform": final_platform,
        "keywords": final_keywords
    }


# 2. clarifier node
MANDATORY_FIELDS = ['organism', 'library_source']
clarifier_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", 
         "You are a helpful SRA assistant. A user is attempting to query the SRA, but is missing critical information.\n"
         "Based on the following list of MISSING_FIELDS, generate a single, polite, and encouraging question asking the user to provide the missing data.\n"
         "Be concise and suggest common examples (e.g., Human/Mouse for organism, RNA-Seq/WGS for strategy)."),
        ("human", "MISSING_FIELDS: {missing_fields}")
    ]
)

clarifier_chain = clarifier_prompt | llm # we don't need structured output here. Just text.

def clarifier(state: SRAQueryState) -> Dict[str, Any]:

    # Identify all fields that are currently None
    missing_fields = [field for field in MANDATORY_FIELDS if state.get(field) is None]

    # Generate the clarification question using the missing fields string
    missing_fields_str = ','.join(missing_fields)
    clarification_text = clarifier_chain.invoke({
        "missing_fields": missing_fields_str
    }).content

    # Format results as an AIMessage
    clarification_message = AIMessage(content=clarification_text)

    return {"messages": [clarification_message]}

# Router for checking if all required info has been filled
def check_slots(state: SRAQueryState) -> str:

    if state.get("organism") is not None and state.get("library_source") is not None:
        return "ready_to_query"
    else:
        return "missing_info"

# 3. sql_compiler node

SQL_SYSTEM_PROMPT = """
You are a SQL WHERE clause expert for the NIH SRA BigQuery dataset.
Table: `nih-sra-datastore.sra.metadata`

Available Columns & Values:
- `organism` - organism name (e.g., 'Homo sapiens', 'Mus musculus')
- `librarysource` - Library source type:
    * TRANSCRIPTOMIC - RNA/mRNA sequencing
    * GENOMIC - DNA/genome sequencing
    * METAGENOMIC - community/environmental DNA
    * TRANSCRIPTOMIC SINGLE CELL - single-cell RNA-seq
    * GENOMIC SINGLE CELL - single-cell DNA
    * VIRAL RNA, SYNTHETIC, OTHER
- `libraryselection` - How the library was prepared (PCR, cDNA, ChIP, RT-PCR, CAGE, MNase, etc.)
- `librarylayout` - SINGLE or PAIRED end
- `platform` - ILLUMINA, OXFORD_NANOPORE, PACBIO, ION_TORRENT, HELICOS, etc.
- `mbases` - megabases of data (numeric)
- `releasedate` - release date (timestamp)
- `center_name` - Research center/institution (use for keyword search like lung, cancer, etc.)
- `sra_study` - Study/project accession identifier (e.g., 'DRP001031', 'SRP012461')
- `acc`, `bioproject` - identifiers (use for specific accession numbers only)

TASK: Generate ONLY the WHERE clause (no SELECT, no FROM, no WHERE keyword itself).

Rules:
- Use exact string matches for categorical fields (organism, librarysource, platform)
- Use UPPER() for librarysource (e.g., 'TRANSCRIPTOMIC' not 'transcriptomic')
- For keywords (biological terms, diseases, conditions):
    * Search in `center_name` column using: LOWER(center_name) LIKE '%keyword%'
    * Use multiple LIKE conditions for multiple keywords
    * Example: LOWER(center_name) LIKE '%lung%' AND LOWER(center_name) LIKE '%cancer%'
- Join all conditions with AND
- Return empty string if no filters apply

KEYWORD SEARCH STRATEGY: (CRITICAL)
The user is searching for biological terms (e.g., "lung", "cancer", "p53").
Most biological metadata is hidden inside the nested `attributes` column or the `sample_name`.
You MUST search these locations for EVERY keyword.

**For a keyword 'X', generate this block:**
```sql
(
  LOWER(sample_name) LIKE '%x%'
  OR LOWER(library_name) LIKE '%x%'
  OR LOWER(center_name) LIKE '%x%'
  OR EXISTS(SELECT 1 FROM UNNEST(attributes) as attr WHERE LOWER(attr.v) LIKE '%x%')
)

Previous Error: {error_context}
(If an error is listed above, fix the WHERE clause to resolve it.)

Search Parameters:
- Organism: {organism}
- Library Source: {source}
- Keywords: {keywords}

Output ONLY the WHERE clause conditions (without the WHERE keyword).
Example: "organism = 'Homo sapiens' AND librarysource = 'TRANSCRIPTOMIC'"
"""

def sql_compiler(state: SRAQueryState) -> Dict[str, Any]:

    print("---Generating SQL WHERE clause---")
    # Prepare context
    error_msg = state.get("error_message", "")
    error_context = f"The previous query failed: {error_msg}" if error_msg else "None"

    # Prepare parameters for prompt
    params = {
        "organism": state["organism"],
        "source": state.get("library_source", ""),
        "keywords": ", ".join(state.get("keywords", [])),
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
        print(f"   Dropped invalid columns: {dropped}")

    # Fall back to defaults if all columns were invalid
    if not safe_columns:
        safe_columns = DEFAULT_COLUMNS
        print(f"   All requested columns invalid, using defaults: {DEFAULT_COLUMNS}")

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
    print(f"   WHERE clause: {where_clause if where_clause else '(empty - will use 1=1)'}")
    print(f"   Full COUNT SQL:\n{count_sql.strip()}")
    print(f"   Full SAMPLE SQL:\n{sample_sql.strip()}")

    # Increment retry count and reset error message
    retry_count = state.get("retry_count", 0) + 1
    return {
        "count_sql": count_sql.strip(),
        "generated_sql": sample_sql.strip(),
        "error_message": None,
        "retry_count": retry_count
    }

# 4. BigQuery executor node
# Connects to the real NIH SRA BigQuery dataset
def bq_executor(state: SRAQueryState) -> Dict[str, Any]:

    try:
        # Initialize BigQuery client (uses injected credentials or environment)
        client = get_bq_client()

        total_count = None

        # Stage 1: Run count query if available (cheap, no column scan)
        count_sql = state.get('count_sql')
        if count_sql:
            print(f"---Executing COUNT query---")
            print(f"SQL: {count_sql[:100]}...")
            count_job = client.query(count_sql)
            count_result = list(count_job.result())
            if count_result:
                total_count = count_result[0]["total"]
            print(f"   Found {total_count:,} total matching records")

        # Stage 2: Run sample query (limited to 100 rows)
        sample_sql = state['generated_sql']
        print(f"---Executing SAMPLE query (LIMIT 100)---")
        print(f"SQL: {sample_sql[:100]}...")

        # Configure query job with reduced billing limit for samples
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=5 * 10**9  # 5 GB cap for sample queries
        )

        # Execute sample query
        query_job = client.query(sample_sql, job_config=job_config)

        # Convert results to list of dictionaries
        results = [dict(row) for row in query_job.result()]
        print(f"   Retrieved {len(results)} sample records")

        return {
            "query_results": results,
            "total_count": total_count,
            "error_message": None
        }

    except Exception as e:
        # Capture BigQuery errors (invalid schema, syntax, auth, etc.)
        error_msg = str(e)
        print(f"   BigQuery Error: {error_msg}")
        return {"error_message": error_msg}

# Router to verify successful execution of SQL query
def check_execution(state: SRAQueryState) -> Literal["success", "zero_results", "sql_error", "max_retries"]:
    """
    Determines the next step based on the execution output.
    """

    error = state.get("error_message")
    results = state.get("query_results")
    retry_count = state.get("retry_count", 0)

    # Check if we've hit max retries (max 3 attempts)
    if error and retry_count >= 3:
        return "max_retries"

    if error:
        return "sql_error"

    # if results list empty, criteria was too strict
    if results is not None and len(results) == 0:
        return "zero_results"

    if results and len(results) > 0:
        return "success"

# 5. Response synthesizer node
# Generates conversational summaries and logs results

synthesis_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a helpful SRA assistant. Summarize the query results for a researcher.\n"
     "When summarizing:\n"
     "1. First, confirm what was searched (organism, library_source, keywords)\n"
     "2. Report dataset count and platforms represented\n"
     "3. Highlight notable studies or patterns\n"
     "Keep the summary concise and actionable."),
    ("human", "Search: {organism} {strategy} {keywords}\nFound {count} datasets:\n{sample}")
])

error_synthesis_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a helpful SRA assistant. The user's query encountered an error.\n"
     "Explain the error in plain language and suggest how they might refine their search."),
    ("human", "Error: {error}\nSearch was: {organism} {strategy} {keywords}")
])

def _write_results_log(state: SRAQueryState, thread_id: str) -> None:
    """Write query results and metadata to a JSON log file."""
    results = state.get("query_results", [])
    total_count = state.get("total_count")
    log_data = {
        "thread_id": thread_id,
        "timestamp": datetime.now().isoformat(),
        "query_params": {
            "organism": state.get("organism"),
            "library_source": state.get("library_source"),
            "platform": state.get("platform"),
            "keywords": state.get("keywords")
        },
        "query_stats": {
            "total_matching_records": total_count,
            "sample_count": len(results) if results else 0
        },
        "count_sql": state.get("count_sql"),
        "sample_sql": state.get("generated_sql"),
        "results": results
    }

    log_path = f"sra_results_{thread_id}.json"
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)
    print(f"   (Results logged to {log_path})")

def response_synthesizer(state: SRAQueryState) -> Dict[str, Any]:
    """Synthesize conversational response for all query outcomes."""
    results = state.get("query_results", [])
    error = state.get("error_message")
    retry_count = state.get("retry_count", 0)
    total_count = state.get("total_count")

    organism = state.get("organism", "unknown")
    source = state.get("library_source", "unknown")
    keywords = ", ".join(state.get("keywords", [])) if state.get("keywords") else "none"

    try:
        if error and retry_count >= 3:
            # Max retries exceeded
            summary = (
                error_synthesis_prompt | llm | StrOutputParser()
            ).invoke({
                "error": error,
                "organism": organism,
                "strategy": source,
                "keywords": keywords
            })
            message = f"Unfortunately, the query couldn't be fixed after {retry_count} attempts.\n\n{summary}"

        elif error:
            # Error but not max retries (shouldn't happen with current routing)
            summary = (
                error_synthesis_prompt | llm | StrOutputParser()
            ).invoke({
                "error": error,
                "organism": organism,
                "strategy": source,
                "keywords": keywords
            })
            message = summary

        elif results is not None and len(results) == 0:
            # No results found
            summary = (
                error_synthesis_prompt | llm | StrOutputParser()
            ).invoke({
                "error": "No datasets matched the search criteria.",
                "organism": organism,
                "strategy": source,
                "keywords": keywords
            })
            message = summary

        else:
            # Success - check if result set is very large and suggest narrowing
            if total_count and total_count > 10000:
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
                # Standard summary for normal-sized result sets
                sample_results = json.dumps(results[:10], indent=2)
                total_str = f"{total_count:,} total, showing {len(results)}" if total_count else f"{len(results)}"
                summary = (
                    synthesis_prompt | llm | StrOutputParser()
                ).invoke({
                    "organism": organism,
                    "strategy": source,
                    "keywords": keywords,
                    "count": total_str,
                    "sample": sample_results
                })
                message = summary

    except Exception as e:
        message = f"Error generating summary: {str(e)}"

    return {"messages": [AIMessage(content=message)]}

workflow = StateGraph(SRAQueryState)

# Add all our nodes
workflow.add_node("extract_params", param_extractor)
workflow.add_node("ask_clarification", clarifier)
workflow.add_node("generate_sql", sql_compiler)
workflow.add_node("execute_query", bq_executor)
workflow.add_node("synthesize_response", response_synthesizer)

# Set the Entry Point
workflow.set_entry_point("extract_params")

# After extraction, decide: Ask user OR Write SQL?
workflow.add_conditional_edges(
    "extract_params",
    check_slots,
    {
        "missing_info": "ask_clarification",
        "ready_to_query": "generate_sql"
    }
)

workflow.add_edge("ask_clarification", "synthesize_response")
workflow.add_edge("generate_sql", "execute_query")

# After SQL Query, determine path based on results
workflow.add_conditional_edges(
    "execute_query",
    check_execution,
    {
        "sql_error": "generate_sql",        # Loop back to fix the SQL
        "zero_results": "synthesize_response",  # Summarize empty results
        "success": "synthesize_response",   # Summarize found data
        "max_retries": "synthesize_response"  # Give up and summarize
    }
)

# Final edge: synthesizer goes to END
workflow.add_edge("synthesize_response", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

# ============================================================================
# Callable Agent Interface for Programmatic Use
# ============================================================================

def create_sra_agent(credentials: Dict[str, Any] = None) -> Any:
    """
    Factory function to create an SRA agent instance with optional credential injection.

    Args:
        credentials: Optional BigQuery service account credentials dict.
                    If provided, will be used for all BigQuery operations.

    Returns:
        Compiled LangGraph agent (Runnable)
    """
    if credentials:
        set_bq_credentials(credentials)
    return app

def query_sra(agent: Any, message: str, thread_id: str = None) -> Dict[str, Any]:
    """
    Query the SRA agent with a natural language question.

    Args:
        agent: Agent instance from create_sra_agent()
        message: Natural language query (e.g., "Find human transcriptomic data on cancer")
        thread_id: Optional thread ID for conversation persistence.
                  If not provided, generates a new UUID.

    Returns:
        Dictionary containing:
        - 'response': Final synthesized response from the agent
        - 'organism': Extracted organism parameter
        - 'library_source': Extracted library source
        - 'platform': Extracted sequencing platform
        - 'keywords': Extracted search keywords
        - 'results': Query results as list of dicts
        - 'total_count': Total matching records
        - 'error': Error message if any
    """
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [HumanMessage(content=message)]}

    try:
        final_state = agent.invoke(inputs, config=config, recursion_limit=10)

        # Extract response from final message
        response_text = final_state["messages"][-1].content if final_state["messages"] else ""

        return {
            "response": response_text,
            "organism": final_state.get("organism"),
            "library_source": final_state.get("library_source"),
            "platform": final_state.get("platform"),
            "keywords": final_state.get("keywords"),
            "results": final_state.get("query_results"),
            "total_count": final_state.get("total_count"),
            "error": final_state.get("error_message"),
            "thread_id": thread_id
        }
    except Exception as e:
        return {
            "response": None,
            "error": str(e),
            "thread_id": thread_id
        }

def run_chat_loop():
    print("==================================================")
    print("🧬 SRA Agent Prototype (Type 'q' to quit)")
    print("==================================================")
    
    # 1. Create a static configuration for this session.
    # This acts as the key to the Agent's memory.
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        try:
            user_input = input("\nUser: ")
            if user_input.lower() in ["q", "quit", "exit"]:
                print("Goodbye!")
                break
            
            # 2. Prepare input. 
            # With MemorySaver, we ONLY send the *new* message.
            # The graph automatically pulls the existing organism/strategy from memory.
            inputs = {"messages": [HumanMessage(content=user_input)]}

            print("   ... processing ...")

            # 3. Invoke with the CONFIG
            final_state = app.invoke(inputs, config=config, recursion_limit=10)

            # --- OUTPUT HANDLING ---
            # The synthesizer always generates the final response
            last_message = final_state["messages"][-1]
            print(f"\n🤖 Agent: {last_message.content}")

            # Log results to JSON file if we have query results
            if final_state.get("query_results"):
                _write_results_log(final_state, thread_id)
                # Break after successful query completion
                break

            # Debug: Show current slot values
            print(f"   (Debug Slots: Organism={final_state.get('organism')}, Library Source={final_state.get('library_source')})")

        except Exception as e:
            print(f"\n❌ CRITICAL ERROR: {e}")
            break
if __name__ == "__main__":
    run_chat_loop()