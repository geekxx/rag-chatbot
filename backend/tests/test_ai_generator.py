import pytest
from unittest.mock import MagicMock, patch, call
from ai_generator import AIGenerator
from search_tools import CourseSearchTool


class TestAIGeneratorDirectResponse:

    def test_returns_text_when_no_tool_use(self, mock_anthropic_direct):
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_direct):
            gen = AIGenerator(api_key="test-key", model="claude-sonnet-4-5")
            result = gen.generate_response(query="What is 2+2?")
        assert result == "Here is a general answer."

    def test_single_api_call_when_no_tool_use(self, mock_anthropic_direct):
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_direct):
            gen = AIGenerator(api_key="test-key", model="claude-sonnet-4-5")
            gen.generate_response(query="What is 2+2?")
        assert mock_anthropic_direct.messages.create.call_count == 1


class TestAIGeneratorToolCallingFlow:

    def test_two_api_calls_when_tool_use(self, mock_anthropic_tool_then_text):
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "MCP is a protocol for tools."
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_tool_then_text):
            gen = AIGenerator(api_key="test-key", model="claude-sonnet-4-5")
            result = gen.generate_response(
                query="what is MCP",
                tools=[{"name": "search_course_content"}],
                tool_manager=tool_manager,
            )
        assert mock_anthropic_tool_then_text.messages.create.call_count == 2
        assert result == "MCP stands for Model Context Protocol."

    def test_correct_tool_name_is_called(self, mock_anthropic_tool_then_text):
        """execute_tool must be called with the name Claude chose — 'search_course_content'."""
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "some result"
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_tool_then_text):
            gen = AIGenerator(api_key="test-key", model="claude-sonnet-4-5")
            gen.generate_response(
                query="what is MCP",
                tools=[{"name": "search_course_content"}],
                tool_manager=tool_manager,
            )
        tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="what is MCP"
        )

    def test_tool_result_included_in_second_api_call(self, mock_anthropic_tool_then_text):
        """The second API call messages must include a tool_result block."""
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "The tool answer."
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_tool_then_text):
            gen = AIGenerator(api_key="test-key", model="claude-sonnet-4-5")
            gen.generate_response(
                query="what is MCP",
                tools=[{"name": "search_course_content"}],
                tool_manager=tool_manager,
            )
        second_call_params = mock_anthropic_tool_then_text.messages.create.call_args_list[1]
        messages = second_call_params.kwargs.get("messages") or second_call_params.args[0]
        # Last message in the second call should be a user message with tool results
        last_message = messages[-1]
        assert last_message["role"] == "user"
        tool_result_block = last_message["content"][0]
        assert tool_result_block["type"] == "tool_result"
        assert tool_result_block["content"] == "The tool answer."

    def test_second_api_call_excludes_tools(self, mock_anthropic_tool_then_text):
        """Second call must NOT include tools — prevents infinite tool loop."""
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "result"
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_tool_then_text):
            gen = AIGenerator(api_key="test-key", model="claude-sonnet-4-5")
            gen.generate_response(
                query="what is MCP",
                tools=[{"name": "search_course_content"}],
                tool_manager=tool_manager,
            )
        second_call_params = mock_anthropic_tool_then_text.messages.create.call_args_list[1]
        call_kwargs = second_call_params.kwargs
        assert "tools" not in call_kwargs, "Second API call must not include tools"

    def test_tool_use_id_matches_in_result(self, mock_anthropic_tool_then_text):
        """tool_use_id in the tool_result must match the id from the tool_use block."""
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "result"
        with patch("ai_generator.anthropic.Anthropic", return_value=mock_anthropic_tool_then_text):
            gen = AIGenerator(api_key="test-key", model="claude-sonnet-4-5")
            gen.generate_response(
                query="what is MCP",
                tools=[{"name": "search_course_content"}],
                tool_manager=tool_manager,
            )
        second_call_params = mock_anthropic_tool_then_text.messages.create.call_args_list[1]
        messages = second_call_params.kwargs.get("messages") or second_call_params.args[0]
        last_message = messages[-1]
        tool_result_block = last_message["content"][0]
        assert tool_result_block["tool_use_id"] == "toolu_abc123"


class TestAIGeneratorLiveAPI:
    """
    Integration tests against the real Anthropic API.
    These reveal the actual failure: invalid API key, wrong model name, etc.
    Mark these to skip if ANTHROPIC_API_KEY is not set.
    """

    @pytest.fixture(autouse=True)
    def require_api_key(self):
        import os
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))
        # Dotenv path relative to backend/
        load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or key == "your_key_here":
            pytest.skip("ANTHROPIC_API_KEY not set — skipping live API tests")

    def test_live_general_question_no_tool(self):
        """A simple general question must succeed — diagnoses API key and model validity."""
        import os
        from config import config
        gen = AIGenerator(api_key=os.environ["ANTHROPIC_API_KEY"], model=config.ANTHROPIC_MODEL)
        try:
            result = gen.generate_response(query="What is 2 + 2? Answer in one sentence.")
            assert isinstance(result, str)
            assert len(result) > 0
        except Exception as e:
            pytest.fail(
                f"Live API call failed: {type(e).__name__}: {e}\n"
                "LIKELY FIX: Check ANTHROPIC_API_KEY in .env and ANTHROPIC_MODEL in config.py"
            )

    def test_live_api_model_name_is_valid(self):
        """Verifies the configured model name is accepted by the API."""
        import os, anthropic
        from config import config
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        try:
            response = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            assert response.content is not None
        except anthropic.NotFoundError as e:
            pytest.fail(
                f"Model '{config.ANTHROPIC_MODEL}' not found: {e}\n"
                "FIX: Update ANTHROPIC_MODEL in config.py to a valid model ID\n"
                "Valid options: 'claude-sonnet-4-5', 'claude-haiku-4-5-20251001', 'claude-opus-4-6'"
            )
        except anthropic.AuthenticationError as e:
            pytest.fail(f"Authentication failed: {e}\nFIX: Check ANTHROPIC_API_KEY in .env")

    def test_live_tool_use_flow(self, real_empty_vector_store):
        """
        Full tool-use flow with real API: Claude calls search tool, gets result, responds.
        This is the exact flow that causes 'query failed' — failure here is the root cause.
        """
        import os
        from config import config
        from search_tools import ToolManager
        gen = AIGenerator(api_key=os.environ["ANTHROPIC_API_KEY"], model=config.ANTHROPIC_MODEL)
        search_tool = CourseSearchTool(real_empty_vector_store)
        tool_manager = ToolManager()
        tool_manager.register_tool(search_tool)
        try:
            result = gen.generate_response(
                query="Answer this question about course materials: What is MCP?",
                tools=tool_manager.get_tool_definitions(),
                tool_manager=tool_manager,
            )
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(
                f"Live tool-use flow failed: {type(e).__name__}: {e}\n"
                "This is the root cause of 'query failed' in the browser."
            )
