import pytest
from unittest.mock import MagicMock
from search_tools import CourseSearchTool
from vector_store import SearchResults


class TestCourseSearchToolExecute:

    def test_returns_formatted_string_on_success(self, mock_vector_store, sample_search_results):
        """execute() should format and return result text when search succeeds."""
        tool = CourseSearchTool(mock_vector_store)
        result = tool.execute(query="what is MCP")
        assert isinstance(result, str)
        assert "MCP" in result or "Intro to MCP" in result

    def test_includes_course_and_lesson_header(self, mock_vector_store):
        """Result should include course title and lesson number in header."""
        tool = CourseSearchTool(mock_vector_store)
        result = tool.execute(query="what is MCP")
        assert "Intro to MCP" in result
        assert "Lesson 1" in result

    def test_returns_error_string_when_search_errors(self, mock_vector_store, error_search_results):
        """When VectorStore returns an error SearchResults, execute() returns the error string."""
        mock_vector_store.search.return_value = error_search_results
        tool = CourseSearchTool(mock_vector_store)
        result = tool.execute(query="anything")
        assert "Search error" in result  # error string passed through to Claude

    def test_returns_not_found_when_empty(self, mock_vector_store, empty_search_results):
        """When search returns no docs, execute() returns an informative not-found message."""
        mock_vector_store.search.return_value = empty_search_results
        tool = CourseSearchTool(mock_vector_store)
        result = tool.execute(query="obscure topic")
        assert "No relevant content found" in result

    def test_passes_query_to_vector_store(self, mock_vector_store, sample_search_results):
        mock_vector_store.search.return_value = sample_search_results
        tool = CourseSearchTool(mock_vector_store)
        tool.execute(query="specific search term")
        mock_vector_store.search.assert_called_once()
        call_kwargs = mock_vector_store.search.call_args
        assert call_kwargs.kwargs.get("query") == "specific search term" or \
               call_kwargs.args[0] == "specific search term"

    def test_passes_course_name_filter(self, mock_vector_store, sample_search_results):
        mock_vector_store.search.return_value = sample_search_results
        tool = CourseSearchTool(mock_vector_store)
        tool.execute(query="anything", course_name="MCP")
        call_kwargs = mock_vector_store.search.call_args
        assert call_kwargs.kwargs.get("course_name") == "MCP"

    def test_passes_lesson_number_filter(self, mock_vector_store, sample_search_results):
        mock_vector_store.search.return_value = sample_search_results
        tool = CourseSearchTool(mock_vector_store)
        tool.execute(query="anything", lesson_number=3)
        call_kwargs = mock_vector_store.search.call_args
        assert call_kwargs.kwargs.get("lesson_number") == 3

    def test_tracks_sources_after_success(self, mock_vector_store, sample_search_results):
        """last_sources should be populated with label and url after a successful search."""
        mock_vector_store.search.return_value = sample_search_results
        tool = CourseSearchTool(mock_vector_store)
        tool.execute(query="anything")
        assert len(tool.last_sources) == 1
        assert tool.last_sources[0]["label"] == "Intro to MCP - Lesson 1"

    def test_sources_empty_after_error(self, mock_vector_store, error_search_results):
        """last_sources should not be populated when search errors."""
        mock_vector_store.search.return_value = error_search_results
        tool = CourseSearchTool(mock_vector_store)
        tool.execute(query="anything")
        assert tool.last_sources == []


class TestCourseSearchToolWithRealEmptyDB:
    """
    Integration tests against a real but empty ChromaDB.
    These reveal whether an empty collection causes a crash or graceful error.
    EXPECTED: These should pass gracefully — if they raise, the empty-DB path is broken.
    """

    def test_search_empty_db_does_not_raise(self, real_empty_vector_store):
        """Querying an empty VectorStore must not raise — must return SearchResults."""
        try:
            results = real_empty_vector_store.search(query="what is MCP")
            # If we get here it either returned empty results or an error SearchResults
            assert results is not None
            assert hasattr(results, "documents")
        except Exception as e:
            pytest.fail(
                f"VectorStore.search() raised {type(e).__name__} on empty DB: {e}\n"
                "FIX NEEDED: Add count check before query in VectorStore.search()"
            )

    def test_execute_on_empty_db_returns_string(self, real_empty_vector_store):
        """CourseSearchTool.execute() must return a string (not raise) even if DB is empty."""
        tool = CourseSearchTool(real_empty_vector_store)
        try:
            result = tool.execute(query="what is MCP")
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(
                f"CourseSearchTool.execute() raised {type(e).__name__} on empty DB: {e}"
            )

    def test_resolve_course_name_empty_db_does_not_raise(self, real_empty_vector_store):
        """_resolve_course_name on empty catalog must not raise."""
        try:
            result = real_empty_vector_store._resolve_course_name("MCP")
            assert result is None  # no match in empty DB
        except Exception as e:
            pytest.fail(
                f"_resolve_course_name() raised {type(e).__name__} on empty catalog: {e}\n"
                "FIX NEEDED: Guard against empty course_catalog in _resolve_course_name()"
            )
