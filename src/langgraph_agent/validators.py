from pydantic import field_validator
from langgraph_agent.config import ORGANISM_ALIASES, VALID_LIBRARY_SOURCES, LIBRARY_SOURCE_ALIASES, VALID_PLATFORMS, PLATFORM_ALIASES
from langgraph_agent.logging_utils import logger


def normalize_key(s: str) -> str:
    """Collapse separators and whitespace to a single canonical form for matching.

    Treats hyphens, underscores, and runs of whitespace as equivalent so that
    'RNA-seq', 'RNA seq', 'RNASEQ '... and 'OXFORD_NANOPORE', 'oxford nanopore'
    all map to the same lookup key. Used only for *matching* — the canonical
    value returned to the caller is the original (e.g. 'OXFORD_NANOPORE').
    """
    return " ".join(s.upper().replace("-", " ").replace("_", " ").split())


# Precompute normalized lookups once so validators tolerate spacing/punctuation
# variance without rebuilding these dicts on every call.
_VALID_LIBRARY_SOURCES_NORM = {normalize_key(s): s for s in VALID_LIBRARY_SOURCES}
_LIBRARY_SOURCE_ALIASES_NORM = {normalize_key(k): v for k, v in LIBRARY_SOURCE_ALIASES.items()}
_VALID_PLATFORMS_NORM = {normalize_key(s): s for s in VALID_PLATFORMS}
_PLATFORM_ALIASES_NORM = {normalize_key(k): v for k, v in PLATFORM_ALIASES.items()}


def resolve_library_source(v: str) -> str | None:
    """Return the canonical library source for a raw value, or None if unknown.

    Tolerant of spacing/punctuation ('RNA-seq', 'RNA seq' -> 'TRANSCRIPTOMIC').
    Shared by the Pydantic validator and the pre-LLM matcher in nodes.py.
    """
    key = normalize_key(v)
    return _VALID_LIBRARY_SOURCES_NORM.get(key) or _LIBRARY_SOURCE_ALIASES_NORM.get(key)


def resolve_platform(v: str) -> str | None:
    """Return the canonical platform for a raw value, or None if unknown.

    Tolerant of spacing/punctuation ('oxford nanopore' -> 'OXFORD_NANOPORE').
    """
    key = normalize_key(v)
    return _VALID_PLATFORMS_NORM.get(key) or _PLATFORM_ALIASES_NORM.get(key)

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
    # Fix any capitalization errors from user input
    parts = v.strip().split()
    return " ".join([parts[0].capitalize()] + [p.lower() for p in parts[1:]]) if parts else v

@field_validator('library_source')
@classmethod
def validate_library_source(cls, v):
    """Validate and normalize library source values."""
    if v is None:
        return v

    # Reject hallucinated prose (anything over 50 chars is clearly wrong)
    if len(v) > 50:
        logger.warning("Rejecting hallucinated library_source (length=%d)", len(v))
        return None

    resolved = resolve_library_source(v)
    if resolved:
        return resolved

    # Return None on mismatch - triggers clarifier to ask user
    logger.warning("Unknown library source '%s' - will ask for clarification", v[:50])
    return None

@field_validator('platform')
@classmethod
def validate_platform(cls, v):
    """Validate and normalize platform values."""
    if v is None:
        return v

    # Reject hallucinated prose (anything over 30 chars is clearly wrong)
    if len(v) > 30:
        logger.warning("Rejecting hallucinated platform (length=%d)", len(v))
        return None

    resolved = resolve_platform(v)
    if resolved:
        return resolved

    # Return None on mismatch - triggers clarifier to ask user
    logger.warning("Unknown platform '%s' - will ask for clarification", v[:30])
    return None

@field_validator('keywords')
@classmethod
def validate_keywords(cls, v):
    """Validate keywords - reject hallucinated prose."""
    if v is None:
        return v

    # Filter out any keywords that are too long (hallucinated sentences)
    clean_keywords = []
    for kw in v:
        if len(kw) <= 50:  # Keywords should be short
            clean_keywords.append(kw)
        else:
            logger.warning(f"Warning: Rejecting hallucinated keyword (length={len(kw)})")

    return clean_keywords if clean_keywords else None
