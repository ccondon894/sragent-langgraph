from typing import Annotated, TypedDict, List, Optional
from langchain_core.messages import BaseMessage
import operator

class SRAQueryState(TypedDict):
    """This class defines the expected state of an SRA query"""
    # annotate messages
    messages: Annotated[List[BaseMessage], operator.add]

    # Extract SRA parameters
    organism: Optional[str]
    library_source: Optional[str]
    platform: Optional[str]
    keywords: Optional[List[str]]

    # Execution attributes
    count_sql: Optional[str]
    generated_sql: Optional[str]
    query_results: Optional[List[dict]]
    total_count: Optional[int]
    error_message: Optional[str]

    retry_count: int


