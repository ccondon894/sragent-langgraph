# SRA Agent - LangGraph Multi-Agent System

A multi-agent system built with LangGraph for querying scientific genomic data (Sequence Read Archive) using natural language. Features a Streamlit web interface with authentication and rate limiting.

## Overview

This project demonstrates advanced LangGraph patterns through a conversational AI agent that translates natural language queries into BigQuery SQL, executes them against the NCBI Sequence Read Archive (SRA), and returns synthesized results.


## Features

- Natural language interface for complex genomic data queries
- Multi-agent architecture with conditional routing and state management
- Production Streamlit web app with authentication and rate limiting
- Google Vertex AI (Gemini) integration via service account
- BigQuery integration for SRA metadata queries
- Persistent conversation memory across sessions
- Cost protection with query quotas and cooldowns
- Export results as JSON


## Quick Start

### Prerequisites

- Python 3.13 or higher
- GCP service account with:
  - `roles/aiplatform.user` (Agent Platform API access)
  - `roles/bigquery.jobUser` (BigQuery query execution)
- Agent Platform API and BigQuery API enabled in your GCP project

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/langgraph-agent.git
cd langgraph-agent
```

2. Install dependencies with Poetry:
```bash
poetry install
```

3. Set up Streamlit secrets (for web app):
```bash
mkdir -p .streamlit
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
```

4. Configure `.streamlit/secrets.toml`:
```toml
app_password = "your-secure-password"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

### Running the Application

**Web Interface (Production)**:
```bash
streamlit run app.py
```
Access at http://localhost:8501 and enter your password.

**CLI Interface (Legacy)**:
```bash
# Requires GEMINI_API_KEY in .env file
poetry run python sra_agent.py
```

## Usage Examples

Once authenticated, you can ask natural language questions like:

- "Find human transcriptomic data related to cancer"
- "Show me Illumina sequencing data for mouse genomic samples"
- "Get metagenomic studies using PacBio sequencing"
- "Search for nanopore sequencing data from arabidopsis"

The agent will:
1. Extract biological parameters (organism, library source, platform, keywords)
2. Ask clarifying questions if information is missing
3. Generate and execute BigQuery SQL queries
4. Return synthesized results in natural language

## Project Structure

```
├── README.md
├── app.py
├── pyproject.toml
├── src
│   └── langgraph_agent
│       ├── __init__.py 
│       ├── agent.py
│       ├── clients.py
│       ├── config.py
│       ├── graph.py
│       ├── logging_utils.py
│       ├── nodes.py
│       ├── prompts.py
│       ├── routers.py
│       ├── schemas.py
│       ├── state.py
│       └── validators.py
├── tests
└── uv.lock
```

## Rate Limiting

The web app enforces the following limits for cost protection:
- 10 queries per session
- 50 queries per hour (rolling window)
- 10-second cooldown between queries

## GCP Service Account Setup

```bash
# Enable required APIs
gcloud services enable aiplatform.googleapis.com
gcloud services enable bigquery.googleapis.com

# Grant necessary roles
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT_EMAIL" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT_EMAIL" \
  --role="roles/bigquery.jobUser"
```

## Contributing

This is a demonstration project showing LangGraph patterns and multi-agent architectures. Feel free to use it as a reference for your own agents.
