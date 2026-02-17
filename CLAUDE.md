# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A RAG (Retrieval-Augmented Generation) chatbot that answers questions about course materials. Built with a FastAPI backend and vanilla JS frontend, using ChromaDB for vector storage and Claude API for generation.

## Setup & Running

```bash
# Install dependencies (uses uv package manager)
uv sync

# Create .env file with your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=your_key_here

# Start the server (runs on http://localhost:8000)
./run.sh
# OR manually:
cd backend && uv run uvicorn app:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`.

## Architecture

```
frontend/          # Vanilla JS + HTML/CSS, no build step
backend/
  app.py           # FastAPI routes and server entry point
  rag_system.py    # Orchestrator: coordinates all components
  document_processor.py  # Parses docs/, extracts metadata, chunks text
  vector_store.py  # ChromaDB wrapper (persists to ./chroma_db/)
  ai_generator.py  # Anthropic Claude API calls with tool use
  search_tools.py  # Tool definitions for Claude's semantic search
  session_manager.py     # Conversation history (max 2 msgs by default)
  config.py        # All tunable parameters as a dataclass
  models.py        # Pydantic models: Course, Lesson, CourseChunk
docs/              # Course material text files (knowledge base)
```

**Request flow:** User query → `app.py` → `rag_system.py` → Claude API calls `search_tools.py` → `vector_store.py` (ChromaDB) → Claude generates response grounded in retrieved chunks.

On first startup, the system reads all `.txt` files from `docs/`, extracts structured metadata (course title, instructor, lesson links), chunks text (800 chars, 100 overlap), and embeds them with `all-MiniLM-L6-v2` into ChromaDB.

## Key Configuration (`backend/config.py`)

| Parameter | Default | Notes |
|-----------|---------|-------|
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Model for generation |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `CHUNK_SIZE` | 800 | Characters per chunk |
| `CHUNK_OVERLAP` | 100 | Overlap between chunks |
| `MAX_RESULTS` | 5 | Search results per query |
| `MAX_HISTORY` | 2 | Conversation turns retained |
| `CHROMA_PATH` | `./chroma_db` | Vector DB persistence location |

## Adding Course Materials

Drop `.txt` files into `docs/`. The document processor extracts metadata from headers formatted as:
- `Course Title: ...`
- `Instructor: ...`
- `Lesson Links: ...`

Delete `./chroma_db/` and restart to re-index after adding documents.

## Tech Stack

- **Backend**: Python 3.13+, FastAPI, Uvicorn, ChromaDB, sentence-transformers, anthropic SDK
- **Frontend**: Vanilla JS/HTML/CSS, marked.js for markdown rendering
- **Package manager**: `uv` (not pip or poetry)
