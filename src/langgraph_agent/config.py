
DEFAULT_COLUMNS = ["acc", "organism", "librarysource", "platform", "mbases"]

# Valid library source values from BigQuery
VALID_LIBRARY_SOURCES = {
    "TRANSCRIPTOMIC", "GENOMIC", "METAGENOMIC",
    "TRANSCRIPTOMIC SINGLE CELL", "GENOMIC SINGLE CELL",
    "VIRAL RNA", "SYNTHETIC", "OTHER", "METATRANSCRIPTOMIC"
}
# Common aliases for library sources
LIBRARY_SOURCE_ALIASES = {
    "RNA-SEQ": "TRANSCRIPTOMIC",
    "RNA-SEQUENCING": "TRANSCRIPTOMIC",
    "RNASEQ": "TRANSCRIPTOMIC",
    "MRNA": "TRANSCRIPTOMIC",
    "WGS": "GENOMIC",
    "WHOLE GENOME": "GENOMIC",
    "DNA": "GENOMIC",
    "WXS": "GENOMIC",  # Exome is genomic DNA
    "EXOME": "GENOMIC",
    "METAGENOME": "METAGENOMIC",
    "ENVIRONMENTAL": "METAGENOMIC",
}
# Valid platform values
VALID_PLATFORMS = {
    "ILLUMINA", "OXFORD_NANOPORE", "PACBIO_SMRT",
    "ION_TORRENT", "BGISEQ", "DNBSEQ", "HELICOS"
}
# Common platform aliases
PLATFORM_ALIASES = {
    "PACBIO": "PACBIO_SMRT",
    "PB": "PACBIO_SMRT",
    "ONT": "OXFORD_NANOPORE",
    "NANOPORE": "OXFORD_NANOPORE",
}
# Common organism name aliases
ORGANISM_ALIASES = {
    "HUMAN": "Homo sapiens",
    "HOMO SAPIENS": "Homo sapiens",
    "MOUSE": "Mus musculus",
    "MUS MUSCULUS": "Mus musculus",
    "RAT": "Rattus norvegicus",
    "FLY": "Drosophila melanogaster",
    "WORM": "Caenorhabditis elegans",
    "ZEBRAFISH": "Danio rerio",
    "YEAST": "Saccharomyces cerevisiae",
    "ARABIDOPSIS": "Arabidopsis thaliana",
}

MANDATORY_FIELDS = ['organism', 'library_source']