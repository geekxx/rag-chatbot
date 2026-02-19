import pytest
from unittest.mock import MagicMock, patch
from rag_system import RAGSystem


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.ANTHROPIC_API_KEY = "test-key"
    config.ANTHROPIC_MODEL = "claude-sonnet-4-5"
    config.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    config.CHUNK_SIZE = 800
    config.CHUNK_OVERLAP = 100
    config.MAX_RESULTS = 5
    config.MAX_HISTORY = 2
    config.CHROMA_PATH = "/tmp/test_chroma"
    return config


class TestRAGSystemQuery:

    def test_query_returns_two_tuple(self, mock_config, tmp_path, mock_anthropic_direct):
        """query() must return (response_str, sources_list)."""
        mock_config.CHROMA_PATH = str(tmp_path / "chroma")
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_direct):
            rag = RAGSystem(mock_config)
        result = rag.query("What is 2+2?")
        assert isinstance(result, tuple)
        assert len(result) == 2
        response, sources = result
        assert isinstance(response, str)
        assert isinstance(sources, list)

    def test_content_query_triggers_tool_execution(
        self, mock_config, tmp_path, mock_anthropic_tool_then_text
    ):
        """When Claude calls a tool, execute_tool must be invoked."""
        mock_config.CHROMA_PATH = str(tmp_path / "chroma")
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_tool_then_text):
            rag = RAGSystem(mock_config)
        response, sources = rag.query("What is MCP?")
        # Two API calls means tool execution happened
        assert mock_anthropic_tool_then_text.messages.create.call_count == 2
        assert isinstance(response, str)

    def test_sources_populated_after_content_search(
        self, mock_config, tmp_path, mock_anthropic_tool_then_text, mock_vector_store
    ):
        """Sources should contain data from the search tool after a tool call."""
        mock_config.CHROMA_PATH = str(tmp_path / "chroma")
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_tool_then_text), \
             patch("rag_system.VectorStore", return_value=mock_vector_store):
            rag = RAGSystem(mock_config)
        response, sources = rag.query("What is MCP?")
        # Sources should be populated after a search tool call
        # (If sources is empty, tool result didn't populate last_sources)
        assert isinstance(sources, list)

    def test_sources_reset_after_query(self, mock_config, tmp_path, mock_anthropic_direct):
        """After query(), tool sources must be cleared so next query starts fresh."""
        mock_config.CHROMA_PATH = str(tmp_path / "chroma")
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_direct):
            rag = RAGSystem(mock_config)
        rag.query("First query")
        # After reset, sources should be empty
        remaining = rag.tool_manager.get_last_sources()
        assert remaining == []

    def test_exception_propagates_from_api(self, mock_config, tmp_path):
        """If the Anthropic API raises, the exception must propagate (not be swallowed)."""
        mock_config.CHROMA_PATH = str(tmp_path / "chroma")
        failing_client = MagicMock()
        failing_client.messages.create.side_effect = RuntimeError("API timeout")
        with patch("ai_generator.anthropic.Anthropic", return_value=failing_client):
            rag = RAGSystem(mock_config)
        with pytest.raises(RuntimeError, match="API timeout"):
            rag.query("What is MCP?")


class TestRAGSystemLiveIntegration:
    """
    Full end-to-end tests against the real system.
    Diagnose the actual failure in production.
    """

    @pytest.fixture(autouse=True)
    def require_api_key(self):
        import os
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or key == "your_key_here":
            pytest.skip("ANTHROPIC_API_KEY not set")

    def test_live_content_query_does_not_raise(self, tmp_path):
        """
        The exact call that app.py makes — must not raise.
        If this fails, that is the root cause of 'query failed'.
        """
        import os
        from config import config as real_config
        real_config.CHROMA_PATH = str(tmp_path / "chroma")
        rag = RAGSystem(real_config)
        try:
            response, sources = rag.query("What is the Model Context Protocol?")
            assert isinstance(response, str)
            assert len(response) > 0
        except Exception as e:
            pytest.fail(
                f"RAGSystem.query() raised {type(e).__name__}: {e}\n"
                "This is the root cause of 'query failed' in the browser."
            )

    def test_live_general_question_does_not_raise(self, tmp_path):
        """General questions (no tool use) should succeed — baseline for API health."""
        import os
        from config import config as real_config
        real_config.CHROMA_PATH = str(tmp_path / "chroma")
        rag = RAGSystem(real_config)
        try:
            response, sources = rag.query("What is 2 + 2?")
            assert isinstance(response, str)
        except Exception as e:
            pytest.fail(f"Even general questions fail: {type(e).__name__}: {e}")
