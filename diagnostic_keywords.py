#!/usr/bin/env python3
"""
Diagnostic script to identify which column contains searchable biological/disease keywords.
Testing candidate columns: center_name, library_name, sample_name, sample_name_sam
"""

from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

client = bigquery.Client()

# Base query: Homo sapiens + TRANSCRIPTOMIC (known to have 2.7M records)
base_where = "organism='Homo sapiens' AND librarysource='TRANSCRIPTOMIC'"

candidate_columns = ["center_name", "library_name", "sample_name", "sample_name_sam"]
keywords = ["lung", "cancer"]

print("=" * 80)
print("KEYWORD SEARCH DIAGNOSTICS FOR SRA METADATA")
print("=" * 80)
print(f"\nBase query: {base_where}")
print(f"Keywords to search: {keywords}")
print(f"Candidate columns: {candidate_columns}\n")

# Test 1: Count records with any of the keywords in each column
print("TEST 1: Counting records with 'lung' OR 'cancer' in each column")
print("-" * 80)

for col in candidate_columns:
    where_clause = f"""
    {base_where}
    AND (LOWER({col}) LIKE '%lung%' OR LOWER({col}) LIKE '%cancer%')
    """

    sql = f"""
    SELECT COUNT(*) as total
    FROM `nih-sra-datastore.sra.metadata`
    WHERE {where_clause}
    """

    try:
        result = client.query(sql).result()
        count = list(result)[0]['total']
        print(f"{col:20s}: {count:,} records")
    except Exception as e:
        print(f"{col:20s}: ERROR - {str(e)[:60]}")

# Test 2: Sample actual values from each column to see what they contain
print("\n\nTEST 2: Sample values from each column (first 5 records)")
print("-" * 80)

for col in candidate_columns:
    sql = f"""
    SELECT {col}
    FROM `nih-sra-datastore.sra.metadata`
    WHERE {base_where}
    LIMIT 5
    """

    try:
        result = client.query(sql).result()
        values = [row[col] for row in result]
        print(f"\n{col}:")
        for val in values:
            # Truncate long strings
            val_str = str(val) if val else "(NULL)"
            if len(val_str) > 70:
                val_str = val_str[:67] + "..."
            print(f"  - {val_str}")
    except Exception as e:
        print(f"\n{col}: ERROR - {str(e)[:60]}")

# Test 3: Check which columns are NOT NULL frequently
print("\n\nTEST 3: NULL rate for each column")
print("-" * 80)

for col in candidate_columns:
    sql = f"""
    SELECT
        COUNT(*) as total,
        COUNTIF({col} IS NOT NULL) as non_null
    FROM `nih-sra-datastore.sra.metadata`
    WHERE {base_where}
    """

    try:
        result = client.query(sql).result()
        row = list(result)[0]
        total = row['total']
        non_null = row['non_null']
        null_pct = 100 * (total - non_null) / total if total > 0 else 0
        print(f"{col:20s}: {non_null:,} / {total:,} non-NULL ({100-null_pct:.1f}% coverage)")
    except Exception as e:
        print(f"{col:20s}: ERROR - {str(e)[:60]}")

# Test 4: Search for 'lung' and 'cancer' separately to see which keywords work
print("\n\nTEST 4: Individual keyword search in each column")
print("-" * 80)

for col in candidate_columns:
    print(f"\n{col}:")
    for keyword in keywords:
        sql = f"""
        SELECT COUNT(*) as total
        FROM `nih-sra-datastore.sra.metadata`
        WHERE {base_where}
        AND LOWER({col}) LIKE '%{keyword}%'
        """

        try:
            result = client.query(sql).result()
            count = list(result)[0]['total']
            print(f"  '{keyword:10s}': {count:,} records")
        except Exception as e:
            print(f"  '{keyword:10s}': ERROR - {str(e)[:50]}")

print("\n" + "=" * 80)
print("END OF DIAGNOSTICS")
print("=" * 80)
