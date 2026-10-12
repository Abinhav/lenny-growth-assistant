# The Lenny Growth Assistant

An AI-powered conversational assistant for product management and
growth, designed to answer questions using Lenny's Podcast transcripts.

## Current status

Phase 1: Project foundation.

Implemented:
- FastAPI application
- Environment-based settings
- Root endpoint
- Health endpoint
- Automated API tests

Not implemented yet:
- PostgreSQL persistence
- Chat sessions
- Ollama or cloud model integration
- Agent SDK
- Transcript ingestion and RAG
- Ship 30 for 30 writing skill
- Frontend and Artifact Viewer

## Requirements

- Python 3.13 or a compatible newer version
- PowerShell on Windows

## Setup

Open PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt


## PostgreSQL Setup

The application uses PostgreSQL to persist chat sessions and messages.

### 1. Create the database

Install and start PostgreSQL, then create the database:

```sql
CREATE DATABASE lenny_growth_assistant;
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and set `DATABASE_URL` to match your local PostgreSQL credentials.

Example:

```env
DATABASE_URL=postgresql://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/lenny_growth_assistant
```

Replace `YOUR_POSTGRES_PASSWORD` with your actual PostgreSQL password in `.env` only. URL-encode special characters in the password when required. Never commit `.env` or real credentials.

### 3. Create the database tables

From the project root, run:

```powershell
python -c "from app.db.session import get_db_connection; from app.db.models import create_tables; g = get_db_connection(); conn = next(g); create_tables(conn); g.close(); print('Database tables created successfully.')"
```

### 4. Start the API

```powershell
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to explore the API.

### Session and message endpoints

- `POST /api/v1/sessions` — create a conversation session.
- `GET /api/v1/sessions` — list conversation sessions.
- `POST /api/v1/sessions/{session_id}/messages` — save a user or assistant message.
- `GET /api/v1/sessions/{session_id}/messages` — list messages in a session.

### Run tests

```powershell
python -m pytest -q
```

demo video link :
https://www.loom.com/share/45be0ab81057432f9165835c8418c10a
