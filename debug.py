# Helper script to check attribute structure
from google.cloud import bigquery
client = bigquery.Client()

# Get one row to see the structure of 'attributes'
query = """
SELECT attributes 
FROM `nih-sra-datastore.sra.metadata` 
WHERE ARRAY_LENGTH(attributes) > 0 
LIMIT 1
"""
job = client.query(query)
for row in job:
    print(row['attributes']) 
    # If output looks like [{'k': 'source', 'v': 'lung'}], the prompt above works.
    # If output looks like [{'tag': 'source', 'value': 'lung'}], change 'attr.v' to 'attr.value' in the prompt.