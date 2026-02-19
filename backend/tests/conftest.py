import sys
import os
import json
import pytest
import tempfile
from unittest.mock import MagicMock, patch

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
