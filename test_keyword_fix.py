#!/usr/bin/env python3
"""
Quick test to verify the agent now generates correct SQL for keyword searches.
"""

from sra_agent import app
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

# Test query with keywords
user_query = "Find me some human RNA-seq data related to lung cancer"

print("=" * 80)
print("TESTING AGENT WITH KEYWORD SEARCH")
print("=" * 80)
print(f"\nUser query: {user_query}\n")

# Create a unique thread ID for this conversation
thread_id = "test-keyword-fix"

try:
    # Invoke the app
    result = app.invoke(
        {"messages": [HumanMessage(content=user_query)]},
        config={"configurable": {"thread_id": thread_id}}
    )

    print("Agent response:")
    print(result["messages"][-1].content)

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
