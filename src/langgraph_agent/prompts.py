from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

param_extractor_prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
         "You are an expert SRA Metadata extractor.\n"
         "Your goal is to fill the following JSON schema: {{organism, library_source, platform, keywords}}.\n"
         "Current State: {existing_state_json}\n"
         "Latest User Input: {user_input}\n\n"
         "INSTRUCTIONS:\n"
         "1. Update the Current State with ANY information from the Latest User Input.\n"
         "2. IMPORTANT: If the user provides a single word or short phrase (like 'transcriptomic', 'RNA-seq', 'genomic', 'human'),\n"
         "   interpret it as filling in a missing field from the Current State.\n"
         "3. Organism mapping:\n"
         "   - 'Human' → 'Homo sapiens'\n"
         "   - 'Mouse' → 'Mus musculus'\n"
         "   - Otherwise return the species name as-is\n"
         "4. Library Source mapping (use UPPERCASE):\n"
         "   - 'RNA-seq', 'transcriptomic', 'mRNA', 'RNA' → 'TRANSCRIPTOMIC'\n"
         "   - 'WGS', 'genome', 'genomic', 'DNA' → 'GENOMIC'\n"
         "   - 'metagenome', 'environmental', 'metagenomic' → 'METAGENOMIC'\n"
         "   - 'single cell' with transcriptomic → 'TRANSCRIPTOMIC SINGLE CELL'\n"
         "   - 'single cell' with genomic → 'GENOMIC SINGLE CELL'\n"
         "5. Platform values (UPPERCASE): ILLUMINA, OXFORD_NANOPORE, PACBIO, ION_TORRENT, HELICOS\n"
         "6. Keywords: Extract any biological terms (tissues, diseases, sample types)\n"
         "7. Return the merged JSON with updated values."),
         ("human", "{input}")
    ]
)

clarifier_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", 
         "You are a helpful SRA assistant. A user is attempting to query the SRA, but is missing critical information.\n"
         "Based on the following list of MISSING_FIELDS, generate a single, polite, and encouraging question asking the user to provide the missing data.\n"
         "Be concise and suggest common examples (e.g., Human/Mouse for organism, RNA-Seq/WGS for strategy)."),
        ("human", "MISSING_FIELDS: {missing_fields}")
    ]
)

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
```
Previous Error: {error_context}
(If an error is listed above, fix the WHERE clause to resolve it.)

Search Parameters:
- Organism: {organism}
- Library Source: {source}
- Platform: {platform}
- Keywords: {keywords}

(Empty parameters should be ignored - do not filter on empty values)

Output ONLY the WHERE clause conditions (without the WHERE keyword).
Example: "organism = 'Homo sapiens' AND librarysource = 'TRANSCRIPTOMIC'"
"""

synthesis_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a helpful SRA assistant. Summarize the query results for a researcher.\n"
     "When summarizing:\n"
     "1. First, confirm what was searched\n"
     "2. Report dataset count and platforms represented\n"
     "3. Highlight notable studies or patterns\n"
     "Keep the summary concise and actionable."),
    ("human", "Search criteria: {search}\nFound {count} datasets:\n{sample}")
])

error_synthesis_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a helpful SRA assistant. The user's query encountered an error or returned no results.\n"
     "Explain what happened in plain language and suggest how they might refine their search."),
    ("human", "Error: {error}\nSearch criteria: {search}")
])