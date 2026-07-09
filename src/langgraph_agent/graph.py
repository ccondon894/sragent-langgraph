from langgraph_agent.nodes import param_extractor, clarifier, sql_compiler, bq_executor, response_synthesizer
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph_agent.state import SRAQueryState
from langgraph_agent.schemas import SRAExtraction, SQLComponents
from langgraph_agent.routers import check_slots, check_execution


def build_graph(llm):
    """Build and compile the SRA agent graph for a given LLM.

    The LLM is passed in (not a module global) so both the credentialed
    Vertex AI path and the default path share one graph definition. The
    structured-output chains are built once here and captured by the node
    closures below.
    """
    structured_llm = llm.with_structured_output(SRAExtraction)
    structured_sql_llm = llm.with_structured_output(SQLComponents)

    workflow = StateGraph(SRAQueryState)

    # Add all our nodes. Nodes that need an LLM receive it via closure;
    # bq_executor is pure I/O and takes none.
    workflow.add_node("extract_params", lambda s: param_extractor(s, structured_llm))
    workflow.add_node("ask_clarification", lambda s: clarifier(s, llm))
    workflow.add_node("generate_sql", lambda s: sql_compiler(s, structured_sql_llm))
    workflow.add_node("execute_query", bq_executor)
    workflow.add_node("synthesize_response", lambda s: response_synthesizer(s, llm))

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
            "sql_error": "generate_sql",            # Loop back to fix the SQL
            "zero_results": "synthesize_response",  # Summarize empty results
            "success": "synthesize_response",       # Summarize found data
            "max_retries": "synthesize_response"    # Give up and summarize
        }
    )

    # Final edge: synthesizer goes to END
    workflow.add_edge("synthesize_response", END)

    return workflow.compile(checkpointer=MemorySaver())
