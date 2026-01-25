#!/usr/bin/env python3
"""
Test various query patterns to ensure keyword search works correctly.
"""

from sra_agent import app
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

test_cases = [
    ("Keyword search with single keyword", "Find me human transcriptomic data related to cancer"),
    ("Keyword search with multiple keywords", "I need mouse genomic data about brain development"),
    ("No keywords", "Show me human TRANSCRIPTOMIC data"),
]

print("=" * 80)
print("TESTING VARIOUS QUERY PATTERNS")
print("=" * 80)

for description, user_query in test_cases:
    print(f"\n{description}")
    print(f"Query: {user_query}")
    print("-" * 80)

    thread_id = f"test-{hash(user_query) % 10000}"

    try:
        result = app.invoke(
            {"messages": [HumanMessage(content=user_query)]},
            config={"configurable": {"thread_id": thread_id}}
        )

        response = result["messages"][-1].content
        # Print first 300 chars of response
        preview = response[:300] + "..." if len(response) > 300 else response
        print(f"Response: {preview}\n")

    except Exception as e:
        print(f"Error: {e}\n")

print("=" * 80)
