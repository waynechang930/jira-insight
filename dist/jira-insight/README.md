# Jira Insight - AI-Powered Jira Ticket Analysis

An AI-powered Jira ticket analysis system with vector similarity search and batch AI analysis capabilities.

## Features

- **Single Issue Analysis** - Analyze individual Jira issues using AI
- **Batch AI Analysis** - Batch process multiple Jira issues with attachment support
- **Project Scan** - Scan projects for similar historical issues
- **Multi-AI Support** - OpenAI, RTK LLM, DeepSeek
- **Attachment Analysis** - Auto-download and analyze .txt, .log, .zip, .tar files
- **2FA Support** - Cookie-based authentication for Jira Cloud with 2FA
- **Jira Integration** - Write analysis results back to Jira as comments

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Initialize Database (Optional - for similarity search)

```bash
python init_db.py
```

### 4. Run Application

```bash
python app.py
```

Visit: http://localhost:5000

## Configuration

See `.env.example` for all available configuration options:

- Database connection (PostgreSQL with pgvector)
- Jira credentials (API token or password)
- **2FA Cookie** - For Jira Cloud with 2FA enabled (see BATCH_AI_ANALYSIS.md)
- AI API keys (OpenAI, RTK LLM, DeepSeek)

## Documentation

- [Batch AI Analysis Guide](BATCH_AI_ANALYSIS.md) - Detailed usage guide
- [CLAUDE.md](CLAUDE.md) - Developer documentation

## Project Structure

```
jira-insight/
├── app.py                  # Flask web application
├── etl_service.py          # ETL pipeline for indexing Jira issues
├── init_db.py              # Database initialization
├── templates/
│   └── index.html          # Web UI
├── .env.example            # Environment template
├── requirements.txt        # Python dependencies
├── README.md               # This file
└── BATCH_AI_ANALYSIS.md    # Detailed documentation
```

## License

Internal use only.