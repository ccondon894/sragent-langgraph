import json
import uuid
from datetime import datetime
from typing import Dict, Any

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from langgraph_agent.clients import set_bq_credentials
from langgraph_agent.state import SRAQueryState
from langgraph_agent.graph import build_graph

DEFAULT_MODEL = "gemini-2.5-flash"

def create_sra_agent(credentials: Dict[str, Any] = None) -> Any:
    """
    Factory function to create an SRA agent instance with optional credential injection.

    Args:
        credentials: Optional service account credentials dict for both BigQuery and Vertex AI.
                    If provided, the Vertex AI backend is used for all LLM operations and the
                    same credentials are injected for BigQuery. If omitted, the default
                    google-genai backend is used (expects GOOGLE_API_KEY / env credentials).

    Returns:
        Compiled LangGraph agent (Runnable)
    """
    if credentials:
        set_bq_credentials(credentials)

        # Create an LLM with the Vertex AI backend and service account credentials
        from google.oauth2.service_account import Credentials as ServiceAccountCredentials
        creds = ServiceAccountCredentials.from_service_account_info(
            credentials,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        llm = ChatGoogleGenerativeAI(
            model=DEFAULT_MODEL,
            vertexai=True,
            project=credentials.get("project_id"),
            location="us-central1",
            credentials=creds
        )
    else:
        llm = ChatGoogleGenerativeAI(model=DEFAULT_MODEL)

    return build_graph(llm)

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

def run_chat_loop():
    print("==================================================")
    print("🧬 SRA Agent (Type 'q' to quit)")
    print("==================================================")
    
    # 1. Build an agent for this session (no credentials -> default backend).
    app = create_sra_agent()

    # 2. Create a static configuration for this session.
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
            print(f"\nCRITICAL ERROR: {e}")
            break
if __name__ == "__main__":
    run_chat_loop()