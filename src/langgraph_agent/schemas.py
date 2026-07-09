from pydantic import BaseModel, Field
from typing import Optional, List
from langgraph_agent.config import DEFAULT_COLUMNS
from langgraph_agent.validators import validate_organism, validate_keywords, validate_library_source, validate_platform
class SRAExtraction(BaseModel):
    """Schema for extracting an SRA query parameters from a user's input message"""
    organism: Optional[str] = Field(
        None, description="Species name ONLY. (e.g. 'Homo sapiens', 'Mus musculus')"
    )
    library_source: Optional[str] = Field(
        None, description="MUST be one of: TRANSCRIPTOMIC, GENOMIC, METAGENOMIC, TRANSCRIPTOMIC SINGLE CELL, GENOMIC SINGLE CELL, VIRAL RNA, SYNTHETIC, OTHER. Return null if not mentioned."
    )
    platform: Optional[str] = Field(
        None, description="MUST be one of: ILLUMINA, OXFORD_NANOPORE, PACBIO, ION_TORRENT, HELICOS. Return null if not mentioned."
    )
    keywords: Optional[List[str]] = Field(
        None, description="Short keyword list (e.g., ['cancer', 'lung']). Each keyword should be 1-3 words max."
    )

    
    _v_organism = validate_organism
    _v_keywords = validate_keywords
    _v_library_source = validate_library_source
    _v_platform = validate_platform

class SQLComponents(BaseModel):
    """
    Structured output for SQL WHERE clause and column selection.
    The sql_compiler function will use theres to construct both COUNT and SAMPLE queries.
    """
    where_clause: str = Field(
        description="The WHERE clause conditions (without WHERE keyword)."
        "Use AND for multiple conditions. Return empty string if no filters needed."
    )
    columns: List[str] = Field(
        default=DEFAULT_COLUMNS,
        description="Columns to SELECT. Will be validated against actual schema."
    )
    
    