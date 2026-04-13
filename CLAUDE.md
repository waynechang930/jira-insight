# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Jira Insight is an AI-powered Jira ticket analysis system that uses vector similarity search to find similar historical issues. It consists of a Flask web application for querying and a background ETL pipeline for indexing Jira data.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Jira Data     │────▶│  ETL Service    │────▶│  PostgreSQL     │
│  Center/Cloud  │     │  (etl_service)  │     │  + pgvector     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                              ┌─────────────────┐         │
                              │  Flask App      │◀────────┘
                              │  (app.py)       │
                              └─────────────────┘
```

**Components:**
- **Flask Web App** (`app.py`): REST API serving similarity search and AI analysis
- **ETL Service** (`etl_service.py`): Fetches Jira issues, processes with AI, stores embeddings
- **Database** (`init_db.py`): PostgreSQL with pgvector for vector similarity search

## Common Commands

```bash
# Start the Flask web application (runs on port 5000)
python app.py

# Initialize database schema (creates table and HNSW index)
python init_db.py

# Run the ETL pipeline to ingest Jira issues
python etl_service.py

# Test Jira API connection
python test_jira_conn.py

# Verify vector similarity search works
python verify_similarity.py

# Generate Google improvement report from Jira issues
python potential_report_to_google.py
```

## Environment Variables (`.env`)

Required configuration in `.env`:
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` - PostgreSQL connection
- `JIRA_DOMAIN` - Jira instance URL
- `JIRA_API_TOKEN` - Jira Personal Access Token
- `JIRA_JQL` - JQL query for ETL (e.g., `project in (X,Y) AND status in (Resolved, Closed)`)
- `OPENAI_API_KEY` - OpenAI API key for embeddings
- `USE_RTK_LLM` - Toggle between OpenAI and internal RTK LLM (Y/N)
- `RTK_LLM_API_KEY` - Internal LLM API key when `USE_RTK_LLM=Y`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve web UI |
| `/api/search` | POST | Single issue similarity search |
| `/api/scan_project` | POST | Scan project for issues with ≥80% similarity |
| `/api/analyze` | POST | AI-powered root cause analysis |

## Database Schema

Table `jira_issues`:
- `jira_key` - Jira issue key (unique)
- `summary` - AI-enhanced summary
- `description` - Extracted symptom description
- `resolution` - Resolution logic
- `raw_content` - Raw Jira JSON
- `metadata` - Structured AI output (includes patch_link)
- `embedding` - 1536-dimensional vector (text-embedding-3-small)

HNSW index on `embedding` for fast cosine similarity search.

## Key Dependencies

- Flask, requests, psycopg2, pgvector
- OpenAI SDK for embeddings
- Python dotenv for configuration

## Batch AI Analysis (New Feature)

### Features
- Select AI tool: OpenAI / RTK LLM / DeepSeek
- Output language: English / 繁體中文
- Input: Saved Filter ID or JQL Query
- Filter: by analyzed status, sort by date or key
- Expandable analysis results
- Selective update to Jira (checkboxes)
- Mark updated issues

### API Endpoints
- `POST /api/batch_load_issues` - Load issues from Filter/JQL
- `POST /api/batch_analyze` - AI analyze single issue (with attachments)
- `POST /api/update_jira_comment` - Add analysis as Jira comment

### Attachment Support
- Downloads to `attachments/{issue_key}/`
- Supports: zip, tar, tgz, tar.gz, gz
- Analyzes all .txt files inside archives
- Extracts key logs (error, warning, exception)

### Jira Comment Format
- Converts markdown to Jira wiki format
- Removes HTML tags
- Converts headers, bold, lists