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
from pydantic import BaseModel, Field
import json
from dotenv import load_dotenv

load_dotenv()


class SRAQueryState(TypedDict):

    #1. annotate messages
    messages: Annotated[List[BaseMessage], operator.add]

    #2. The SRA Form. Extracted SRA parameters
    organism: Optional[str]
    library_strategy: Optional[str]  # e.g., 'RNA-Seq'
    platform: Optional[str]          # e.g., 'ILLUMINA'
    keywords: Optional[List[str]]    # e.g., ['lung cancer', 'adenocarcinoma']

    #3. Execution Artifacts
    generated_sql: Optional[str]     # The SQL string
    query_results: Optional[List[dict]] # The rows returned from BigQuery
    error_message: Optional[str]     # If BigQuery fails

    # 4. Control Flags
    is_clarification_needed: bool #Triggered if mandatory slots are missing

# This will be what our param_extractor returns.
# This is like a subset of our SRAQueryState. 
class SRAExtraction(BaseModel):
    """
    Schema for extracting SRA query parameters from user input.
    """
    organism: Optional[str] = Field(
        None, description="The species, e.g., 'Homo sapiens' or 'Mus musculus'."
    )
    library_strategy: Optional[str] = Field(
        None, description="The sequencing strategy, e.g., 'RNA-Seq' or 'WGS'."
    )
    platform: Optional[str] = Field(
        None, description="The sequencing platform, e.g., 'ILLUMINA'."
    )
    keywords: Optional[List[str]] = Field(
        None, description="A list of relevant search keywords, e.g., ['cancer', 'brain']."
    )

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
structured_llm =llm.with_structured_output(SRAExtraction)

### NODES ###

# 1. param_extractor node

param_extractor_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", 
         "You are an expert SRA Metadata extractor.\n "
         "Your goal is to fill the following JSON schema: {{organism, library_strategy, platform, keywords}}.\n"
         "Current State: {existing_state_json} Latest User Input: {user_input}\n"
         "INSTRUCTIONS:\n"
         "1. Update the Current State with information from the Latest User Input.\n"
         "2. If the user mentions 'Human', set organism to 'Homo sapiens'.\n"
         "3. If the user mentions 'Mouse', set organism to 'Mus musculus'.\n"
         "4. Return the merged JSON."),
         ("human", "{input}")
    ]
)

def param_extractor(state: SRAQueryState) -> Dict[str, Any]:

    latest_message = state["messages"][-1].content

    # 1. Get the OLD data (Saved State)
    old_organism = state.get("organism")
    old_strategy = state.get("library_strategy")
    old_platform = state.get("platform")
    old_keywords = state.get("keywords") or []

    # 2. Get the NEW data (LLM Extraction)
    # We pass the old state to the prompt so the LLM knows context, 
    # but we still need to handle the merge logic ourselves.
    current_params = {
        "organism": old_organism, 
        "library_strategy": old_strategy, 
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
    final_strategy = new_data['library_strategy'] if new_data['library_strategy'] else old_strategy
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
        "library_strategy": final_strategy,
        "platform": final_platform,
        "keywords": final_keywords
    }


# 2. clarifier node
MANDATORY_FIELDS = ['organism', 'library_strategy']
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


    if state.get("organism") is not None and state.get("library_strategy") is not None:
        return "ready_to_query"
    else:
        return "missing_info"

# 3. sql_compiler node

SQL_SYSTEM_PROMPT = """
You are an expert SQL compiler.
Target Table: `nih-sra-datastore.sra.metadata`

Columns: 
- `organism` (NOT organism_name)
- `library_strategy`
- `platform`
- `study_title` (for keywords)
- `mbases` (for size)

Previous Error: {error_context}
(If an error is listed above, you MUST fix the SQL to resolve it.)

Parameters:
Organism: {organism}
Strategy: {strategy}
Keywords: {keywords}

Output: RAW SQL ONLY. No markdown backticks.
"""

# set up sql_compiler llm chain
sql_prompt_template = PromptTemplate.from_template(SQL_SYSTEM_PROMPT)
sql_compiler_chain = (
    sql_prompt_template
    | llm 
    | StrOutputParser()
)

def sql_compiler(state: SRAQueryState) -> Dict[str, Any]:

    print("---Generating SQL Query---")
    # Prepare context
    error_msg = state.get("error_message", "")
    error_context = f"The previous query failed: {error_msg}" if error_msg else "None"

    # Prepare parameters for prompt
    params ={
        "organism": state["organism"],
        "strategy": state["library_strategy"],
        "keywords": ", ".join(state.get("keywords", [])),
        "error_context": error_context

    }

    # Invoke
    sql_chain = PromptTemplate.from_template(SQL_SYSTEM_PROMPT) | llm | StrOutputParser()
    raw_response = sql_chain.invoke(params)
    
    clean_sql = raw_response.replace("```sql", "").replace("```", "").strip()

    # Reset error message since we are trying a new query
    return {"generated_sql": clean_sql, "error_message": None}

# 4. BigQuery executor node
# Using mock results for now
def bq_executor(state: SRAQueryState) -> Dict[str, Any]:
    
    sql = state['generated_sql']
    print(f"---Executing SQL: {sql} ---")

    # Simulating a specific failure for testing:
    if "organism_name" in sql: 
        return {"error_message": "Column 'organism_name' not found in schema."}
    

    mock_query_results = [
    {
        "acc": "SRR14624321",
        "bioproject": "PRJNA732109",
        "experiment_title": "RNA-seq of Homo sapiens lung adenocarcinoma cell line A549 treated with Cisplatin",
        "study_title": "Transcriptomic analysis of drug resistant lung cancer cells",
        "organism": "Homo sapiens",
        "library_strategy": "RNA-Seq",
        "library_source": "TRANSCRIPTOMIC",
        "library_layout": "PAIRED",
        "platform": "ILLUMINA",
        "instrument_model": "Illumina NovaSeq 6000",
        "mbases": 6500,  # ~6.5 GigaBases of data
        "release_date": "2023-05-12 00:00:00 UTC",
    },
    {
        "acc": "SRR13899102",
        "bioproject": "PRJNA689102",
        "experiment_title": "Homo sapiens lung biopsy RNA sequencing: control sample 04",
        "study_title": "Gene expression profiling of human lung tissue",
        "organism": "Homo sapiens",
        "library_strategy": "RNA-Seq",
        "library_source": "TRANSCRIPTOMIC",
        "library_layout": "SINGLE",
        "platform": "ILLUMINA",
        "instrument_model": "Illumina HiSeq 2500",
        "mbases": 2100,
        "release_date": "2022-11-08 00:00:00 UTC",
    }
]

    return {"query_results": mock_query_results, "error_message": None}

# Router to verify successful execution of SQL query
def check_execution(state: SRAQueryState) -> Literal["success", "zero_results", "sql_error"]:
    """
    Determines the next step based on the execution output.
    """

    error = state.get("error_message")
    results = state.get("query_results")

    if error:
        return "sql_error"
    
    # if results list empty, criteria was too strict
    if results is not None and len(results) == 0:
        return "zero_results"
    
    if results and len(results) > 0:
        return "success"
    
workflow = StateGraph(SRAQueryState)

# Add all our nodes
workflow.add_node("extract_params", param_extractor)
workflow.add_node("ask_clarification", clarifier)
workflow.add_node("generate_sql", sql_compiler)
workflow.add_node("execute_query", bq_executor)

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

workflow.add_edge("ask_clarification", END)
workflow.add_edge("generate_sql", "execute_query")

# After SQL Query, determine path based on results
workflow.add_conditional_edges(
    "execute_query",
    check_execution,
    {
        "sql_error": "generate_sql", # Loop back to fix the SQL
        "zero_results": END,         # Completed, but no data
        "success": END               # Completed, with data
    }
)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

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
            
            # Case A: Success
            if final_state.get("query_results"):
                results = final_state["query_results"]
                print(f"\n✅ SUCCESS! Found {len(results)} datasets:\n")
                for row in results:
                    print(f"  • {row['acc']} | {row['platform']} | {row['experiment_title'][:60]}...")
                
                # Break or continue depending on if you want to keep chatting
                # For this demo, we break because the SQL is done.
                break

            # Case B: Error
            elif final_state.get("error_message"):
                print(f"\n❌ SYSTEM ERROR: {final_state['error_message']}")

            # Case C: Clarification Needed
            else:
                last_message = final_state["messages"][-1]
                print(f"\n🤖 Agent: {last_message.content}")
                
                # Debug
                print(f"   (Debug Slots: Organism={final_state.get('organism')}, Strategy={final_state.get('library_strategy')})")

        except Exception as e:
            print(f"\n❌ CRITICAL ERROR: {e}")
            break
if __name__ == "__main__":
    run_chat_loop()