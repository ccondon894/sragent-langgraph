# LangGraph Agent Codebase Reference

## Project Overview

This is a sophisticated multi-agent system built with LangGraph for querying scientific data (specifically SRA/genomic data) using natural language. The project contains three main agent implementations with increasing complexity, demonstrating different LangGraph patterns.

**Tech Stack**: Python 3.13+, LangGraph, LangChain, Google Vertex AI (Gemini), Google BigQuery, Poetry

---

## Core Project Structure

```
/langgraph-agent/
├── app.py                    # Streamlit web app (PRODUCTION INTERFACE)
├── sra_agent.py              # Main SRA agent (CORE LOGIC)
├── rate_limiter.py           # Rate limiting for web app
├── agentic_router.py         # Research & writing agent
├── langgraph_query_router.py # Classification-based routing agent
├── first_script.py           # Basic chatbot prototype
├── KEYWORD_SEARCH_FIX.md     # Bug fix documentation
├── DEPLOYMENT.md             # Deployment guide
├── pyproject.toml            # Poetry dependencies
├── requirements.txt          # Streamlit Cloud dependencies
├── .env                      # API keys (TAVILY_API_KEY; legacy GEMINI_API_KEY for CLI)
├── .streamlit/               # Streamlit configuration
│   ├── config.toml           # Theme and server settings
│   └── secrets.toml.template # Secrets template
├── src/langgraph_agent/      # Package directory
└── tests/                    # Test directory
```

---

## Key Files and Purposes

### **app.py** - STREAMLIT WEB APPLICATION (PRODUCTION INTERFACE)
**Purpose**: Production web interface for the SRA agent with authentication, rate limiting, and chat UI.

**Main Components**:
- **Password Authentication**: Secure password gate using `hmac.compare_digest()`
- **Session Management**: Manages conversation state, thread IDs, and rate limiting
- **Chat Interface**: Full conversational UI with message history and response display
- **Rate Limiting**: Enforces query limits (10/session, 50/hour, 30s cooldown)
- **Credentials Integration**: Loads GCP service account from Streamlit secrets for both Vertex AI and BigQuery
- **Export Functionality**: Download query results as JSON

**Key Features**:
- `initialize_session_state()`: Sets up session variables for messages, agent, rate limiter
- `load_gcp_credentials()`: Loads service account credentials from Streamlit secrets
- `create_agent()`: Creates SRA agent with Vertex AI backend using service account
- `handle_user_input()`: Processes user queries with rate limiting and error handling
- Sidebar controls: Query quota display, clear chat, download results, reset agent

**Authentication**: Uses Vertex AI backend (`vertexai=True`) with service account credentials instead of API key.

---

### **sra_agent.py** (770 lines) - CORE AGENT LOGIC
**Purpose**: Full-featured conversational agent for querying SRA (Sequence Read Archive) genomic metadata from BigQuery.

**Main Components**:
- **`SRAQueryState`** (TypedDict): Agent state schema
  - `organism`: Target organism (e.g., "human", "mouse")
  - `library_source`: DNA source type (genomic, transcriptomic, metagenomic)
  - `platform`: Sequencing platform (Illumina, PacBio, nanopore)
  - `keywords`: Search keywords for filtering
  - `messages`: Conversation history

- **`SRAExtraction`** & **`SQLComponents`**: Pydantic models for data validation

- **Key Functions**:
  - `get_valid_columns()`: Fetches BigQuery schema with 24-hour caching
  - `param_extractor()`: Extracts biological parameters from user input using LLM
  - `clarifier()`: Asks clarifying questions for missing parameters
  - `sql_compiler()`: Generates BigQuery SQL queries
  - `bq_executor()`: Executes queries on BigQuery with retry logic
  - `response_synthesizer()`: Generates natural language responses from query results
  - `run_chat_loop()`: Main interactive chat interface with persistent memory

**Architecture**: Uses conditional edge routing to flow between parameter extraction, clarification, SQL compilation, and execution stages.

**State Persistence**: Uses `MemorySaver` for conversation memory across turns; thread IDs track separate sessions.

---

### **agentic_router.py** (185 lines) - RESEARCH & WRITING AGENT
**Purpose**: Multi-agent research and writing workflow demonstrating tool use and conditional routing.

**Key Components**:
- **`GraphState`**: Tracks messages, research topic, research notes, and final summary
- **`research_node()`**: LLM-powered research assistant that gathers information
- **`tool_node`**: Automatically executes Tavily web searches
- **`writer_node()`**: Synthesizes research findings into polished summaries
- **Routing Logic**: Conditionally routes to tool execution and writing based on agent decisions

**Pattern**: Demonstrates multi-node routing and tool integration in LangGraph.

---

### **langgraph_query_router.py** (201 lines) - MESSAGE CLASSIFICATION AGENT
**Purpose**: Simple classification-based routing system that demonstrates branching logic.

**Key Components**:
- **`GraphState`**: Tracks messages and routing decision
- **`classify_input()`**: Routes input as "greeting" or "question" using LLM
- **`handle_greeting()`**: Responds to user greetings
- **`handle_question()`**: Processes questions (with semantic search mentioned but not fully implemented)
- **Conditional Routing**: Simple if/else branching based on classification

**Pattern**: Demonstrates basic message classification and branching patterns.

---

### **rate_limiter.py** - RATE LIMITING MODULE
**Purpose**: Cost protection and query throttling for the Streamlit web app.

**Main Components**:
- **`RateLimitConfig`**: Configuration dataclass with limits:
  - `max_queries_per_session = 10`
  - `max_queries_per_hour = 50`
  - `cooldown_seconds = 30`
- **`SessionRateLimiter`**: Rate limiting logic using Streamlit session state
  - `can_query() -> (bool, reason)`: Checks if query is allowed
  - `record_query()`: Records query timestamp
  - `get_remaining_queries()`: Returns quota information
  - `reset_session()`: Resets session counter

**Pattern**: Session-based rate limiting with hourly rolling window and cooldown enforcement.

---

### **first_script.py** (90 lines) - BASIC PROTOTYPE
**Purpose**: Simple chatbot prototype showing basic LangGraph patterns.

**Components**:
- **`ChatState`**: Tracks message history
- **`call_model()`**: Invokes LLM with conversation context
- Demonstrates simple message accumulation pattern

---

### **KEYWORD_SEARCH_FIX.md** - CRITICAL BUG DOCUMENTATION
**Important Fix**: Documents a bug where keyword searches were being performed in the wrong BigQuery column.
- **Issue**: Keywords were searched in `sra_study` column instead of `center_name`
- **Impact**: Returned incorrect results for keyword-based queries
- **Solution**: Corrected the column reference in the SQL compilation logic
- **Status**: Fixed and verified

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `langchain` | Core LLM and chain framework |
| `langgraph` | Graph-based agent orchestration and state management |
| `langchain-google-genai` | Google Vertex AI (Gemini) integration via service account auth |
| `google-cloud-bigquery` | BigQuery database queries |
| `langgraph-checkpoint-sqlite` | Persistent conversation state storage |
| `tavily-python` | Web search integration |
| `python-dotenv` | Environment variable loading |

---

## Main Entry Points

### 1. **app.py** - PRODUCTION WEB APPLICATION
Streamlit web interface with authentication and rate limiting (deployed to Streamlit Community Cloud).

**Running locally**:
```bash
streamlit run app.py
```

**Features**:
- Password-protected access
- Full chat interface with persistent conversation memory
- Rate limiting (10 queries/session, 50/hour, 30s cooldown)
- Vertex AI backend using GCP service account
- BigQuery integration for SRA data queries
- Download results as JSON

**Authentication**: Requires GCP service account with `roles/aiplatform.user` and `roles/bigquery.jobUser`.

### 2. **sra_agent.py::run_chat_loop()** - CLI INTERFACE
Interactive command-line chat loop for SRA queries (legacy interface).

**Running**:
```bash
poetry run python sra_agent.py
```

**Features**:
- Creates a persistent thread ID for memory
- Accepts natural language queries like: "Find human transcriptomic data related to cancer"
- Returns BigQuery results with synthesized responses
- Maintains conversation context across multiple turns

**Authentication**: Uses API key from `.env` file (`GEMINI_API_KEY`).

### 3. **agentic_router.py**
Research and writing pipeline (runnable as script).

### 4. **langgraph_query_router.py**
Classification-based routing system (runnable as script).

---

## Architecture Patterns

### SRA Agent Workflow (sra_agent.py)

```
User Query
    ↓
param_extractor (Extract organism, library source, platform, keywords)
    ↓
check_slots (All parameters present?)
    ├─ NO → clarifier (Ask user for missing info) → loop back
    └─ YES ↓
sql_compiler (Generate BigQuery SQL)
    ↓
bq_executor (Execute query on BigQuery)
    ↓
check_execution (Did query succeed?)
    ├─ FAILED → (Error message)
    ├─ NO_RESULTS → (Zero results message)
    └─ SUCCESS ↓
response_synthesizer (Generate natural response)
    ↓
Return to User
```

### Key Design Patterns

1. **Conditional Edge Routing**: Routes flow based on state checks (e.g., `check_slots`, `check_execution`)
2. **State Persistence**: Uses `MemorySaver` for conversation memory across agent invocations
3. **Type-Safe State**: Uses TypedDict and Pydantic for state validation
4. **Cached Schema**: BigQuery schema cached for 24 hours to minimize API calls
5. **Error Recovery**: Retry logic in `bq_executor` for transient failures
6. **Tool Integration**: Demonstrates both tool-use agents (agentic_router) and deterministic agents (sra_agent)

---

## Configuration

### Authentication

**Streamlit App** (app.py):
- Uses **GCP Service Account** for both Vertex AI and BigQuery
- Credentials loaded from Streamlit secrets (`st.secrets["gcp_service_account"]`)
- LLM backend: Vertex AI via `vertexai=True` parameter
- Required GCP roles:
  - `roles/bigquery.jobUser` - Execute BigQuery queries
  - `roles/aiplatform.user` - Access Vertex AI (Gemini models)

**CLI Scripts** (sra_agent.py, agentic_router.py):
- Legacy support for API key authentication via `.env` file
- Environment Variables (.env):
  ```
  GEMINI_API_KEY=...        # Google Generative AI API key (CLI only)
  TAVILY_API_KEY=...        # Tavily web search API key
  ```

### Python Version
- Requires Python 3.13+

### Dependency Management
- Uses Poetry (pyproject.toml)
- Run `poetry install` to set up environment

### GCP Service Account Setup

For Streamlit app deployment, configure service account with:

```bash
# Enable required APIs
gcloud services enable aiplatform.googleapis.com
gcloud services enable bigquery.googleapis.com

# Grant Vertex AI User role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT_EMAIL" \
  --role="roles/aiplatform.user"

# Grant BigQuery Job User role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT_EMAIL" \
  --role="roles/bigquery.jobUser"
```

---

## Known Issues & Fixes

### ✅ Keyword Search Fix (RESOLVED)
- **Issue**: Keyword searches performed on wrong BigQuery column
- **Details**: See `KEYWORD_SEARCH_FIX.md`
- **Status**: Fixed in current version

---

## Common Tasks

### Running the Streamlit Web App (Production Interface)
```bash
# Run locally
streamlit run app.py

# Access at http://localhost:8501
# Enter password (configured in .streamlit/secrets.toml)
# Start chatting with the SRA agent
```

### Running the CLI Agent (Legacy Interface)
```bash
# Start interactive command-line chat loop
poetry run python sra_agent.py
```

### Querying BigQuery
The agent automatically:
1. Extracts parameters from natural language input (organism, library source, platform, keywords)
2. Validates parameters against BigQuery schema
3. Generates and executes SQL queries
4. Returns synthesized responses with sample results

### Adding New Parameters
To add a new query parameter:
1. Update `SRAQueryState` in sra_agent.py
2. Update `param_extractor()` to extract the new parameter
3. Update `clarifier()` to ask for it if missing
4. Update `sql_compiler()` to include it in SQL

### Deploying to Streamlit Community Cloud
See `DEPLOYMENT.md` for comprehensive deployment guide.

**Quick steps**:
1. Push code to GitHub
2. Connect repository to Streamlit Community Cloud
3. Configure secrets in Streamlit dashboard:
   - `app_password`: Password for web app
   - `gcp_service_account`: Full service account JSON
4. Deploy and verify

**Prerequisites**:
- GCP service account with `roles/aiplatform.user` and `roles/bigquery.jobUser`
- Vertex AI API enabled in GCP project
- BigQuery API enabled in GCP project

---

## Testing & Debugging

**Test Suite**:
- 67 total tests (57 unit/integration, 10 live API tests)
- Comprehensive mocking to minimize API costs
- Cost tracking and limits enforced
- Run tests: `pytest tests/`
- Run live API tests: `pytest -m live` (requires credentials)

**Test Coverage**:
- Parameter extraction and validation
- SQL query generation and compilation
- Rate limiting enforcement
- Agent interface and credential injection
- Error handling and recovery
- End-to-end workflows

**Note**: Test files (test_*.py, diagnostic_*.py, debug.py) are for development/experimentation. Live API tests are skipped by default to avoid costs.

---

## Project History

- **Current State**: Production-ready Streamlit web app with Vertex AI backend
- **Latest Milestones**:
  - Milestone 10: Switched to Vertex AI backend with service account auth
  - Milestone 9: Deployed to Streamlit Community Cloud
  - Milestone 8: Added error handling and UI polish
  - Milestone 7: Created deployment configuration
  - Milestone 6: Built comprehensive test suite with mocking
  - Milestones 1-5: Refactored agent for web use, built Streamlit UI, integrated BigQuery
- **Focus**: Building increasingly sophisticated LangGraph agents with production deployment
- **Evolution**: From basic chatbot → message classification → multi-agent research → full SRA query system → production web app
