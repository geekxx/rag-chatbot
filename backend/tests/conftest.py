import sys
import os
import json
import pytest
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

# Add backend/ to path so tests can import backend modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vector_store import VectorStore, SearchResults
from search_tools import CourseSearchTool, CourseOutlineTool, ToolManager


@pytest.fixture
def sample_search_results():
    """Real SearchResults with one doc and metadata entry."""
    return SearchResults(
        documents=["MCP stands for Model Context Protocol. It enables tool use."],
        metadata=[{"course_title": "Intro to MCP", "lesson_number": 1}],
        distances=[0.25],
    )


@pytest.fixture
def empty_search_results():
    return SearchResults(documents=[], metadata=[], distances=[])


@pytest.fixture
def error_search_results():
    return SearchResults.empty("Search error: Number of requested results 5 is greater than number of elements in index 0")


@pytest.fixture
def mock_vector_store(sample_search_results):
    """VectorStore mock that returns canned results by default."""
    store = MagicMock(spec=VectorStore)
    store.search.return_value = sample_search_results
    store.get_lesson_link.return_value = "https://example.com/lesson/1"
    store.get_course_outline.return_value = {
        "title": "Intro to MCP",
        "course_link": "https://example.com/course",
        "lessons": [
            {"lesson_number": 1, "lesson_title": "Introduction", "lesson_link": None},
            {"lesson_number": 2, "lesson_title": "Tool Use", "lesson_link": None},
        ],
    }
    return store


@pytest.fixture
def real_empty_vector_store(tmp_path):
    """Actual VectorStore backed by a fresh temporary ChromaDB — zero documents."""
    return VectorStore(
        chroma_path=str(tmp_path / "chroma_test"),
        embedding_model="all-MiniLM-L6-v2",
        max_results=5,
    )


def make_text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def make_tool_use_block(tool_name, tool_id, input_dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.id = tool_id
    block.input = input_dict
    return block


@pytest.fixture
def mock_anthropic_direct():
    """Client whose first create() call returns a plain text response (no tool use)."""
    client = MagicMock()
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [make_text_block("Here is a general answer.")]
    client.messages.create.return_value = response
    return client


@pytest.fixture
def mock_anthropic_tool_then_text(mock_vector_store):
    """
    Client whose first create() returns tool_use for search_course_content,
    second create() returns a plain text answer.
    """
    client = MagicMock()

    first_response = MagicMock()
    first_response.stop_reason = "tool_use"
    first_response.content = [
        make_tool_use_block(
            "search_course_content",
            "toolu_abc123",
            {"query": "what is MCP"},
        )
    ]

    second_response = MagicMock()
    second_response.stop_reason = "end_turn"
    second_response.content = [make_text_block("MCP stands for Model Context Protocol.")]

    client.messages.create.side_effect = [first_response, second_response]
    return client


# ============================================================================
# FastAPI Test App & Client Fixtures
# ============================================================================


@pytest.fixture
def test_app():
    """
    Create a FastAPI test app with all endpoints but no static file mounting.
    This avoids import errors from missing ../frontend directory.
    """
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from pydantic import BaseModel
    from typing import List, Optional

    app = FastAPI(title="Course Materials RAG System - Test", root_path="")

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # Request/Response models
    class QueryRequest(BaseModel):
        query: str
        session_id: Optional[str] = None

    class SourceItem(BaseModel):
        label: str
        url: Optional[str] = None

    class QueryResponse(BaseModel):
        answer: str
        sources: List[SourceItem]
        session_id: str

    class CourseStats(BaseModel):
        total_courses: int
        course_titles: List[str]

    # Inject mock RAG system via dependency
    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        """Process a query and return response with sources"""
        try:
            rag_system = app.state.rag_system
            session_id = request.session_id
            if not session_id:
                session_id = rag_system.session_manager.create_session()

            answer, sources = rag_system.query(request.query, session_id)

            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        """Get course analytics and statistics"""
        try:
            rag_system = app.state.rag_system
            analytics = rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/session/{session_id}")
    async def clear_session(session_id: str):
        """Clear conversation history for a session"""
        rag_system = app.state.rag_system
        rag_system.session_manager.clear_session(session_id)
        return {"status": "cleared", "session_id": session_id}

    return app


@pytest.fixture
def mock_rag_system(tmp_path):
    """
    Create a mock RAG system with real SessionManager but mocked components.
    This allows testing endpoint request/response handling without API calls.
    """
    from rag_system import RAGSystem
    from config import Config
    from unittest.mock import MagicMock

    # Create a config with temp directory for tests
    test_config = Config()
    test_config.CHROMA_PATH = str(tmp_path / "chroma_test")
    test_config.ANTHROPIC_API_KEY = "test-key"

    # Create RAG system
    rag_system = RAGSystem(test_config)

    # Mock the AI generator to return predictable responses
    rag_system.ai_generator.generate_response = MagicMock(
        return_value="Test response about course materials"
    )

    # Mock tool manager sources
    rag_system.tool_manager.get_last_sources = MagicMock(
        return_value=[
            {"label": "Lesson 1: Introduction", "url": "https://example.com/lesson/1"}
        ]
    )
    rag_system.tool_manager.reset_sources = MagicMock()

    return rag_system


@pytest.fixture
def test_client(test_app, mock_rag_system):
    """
    Create a TestClient with the test app and inject mock RAG system.
    This provides a complete test environment for API testing.
    """
    test_app.state.rag_system = mock_rag_system
    return TestClient(test_app)


@pytest.fixture
def test_data():
    """
    Fixture providing common test data for API tests.
    """
    return {
        "sample_query": "What is machine learning?",
        "sample_query_request": {
            "query": "What is machine learning?",
            "session_id": None,
        },
        "expected_sources": [
            {"label": "Lesson 1: Introduction", "url": "https://example.com/lesson/1"}
        ],
    }
