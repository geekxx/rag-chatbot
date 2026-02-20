import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException


class TestQueryEndpoint:
    """Tests for POST /api/query endpoint"""

    def test_query_endpoint_success(self, test_client, test_data):
        """Query endpoint returns correct response structure"""
        response = test_client.post("/api/query", json=test_data["sample_query_request"])

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert "session_id" in data
        assert data["answer"] == "Test response about course materials"

    def test_query_endpoint_creates_session_if_not_provided(self, test_client, test_data):
        """Query endpoint creates a new session when session_id is not provided"""
        request_data = {"query": test_data["sample_query"]}
        response = test_client.post("/api/query", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] is not None
        assert data["session_id"].startswith("session_")

    def test_query_endpoint_preserves_session_id(self, test_client, test_data, mock_rag_system):
        """Query endpoint uses provided session_id"""
        # Create a session first
        session_id = mock_rag_system.session_manager.create_session()

        request_data = {"query": test_data["sample_query"], "session_id": session_id}
        response = test_client.post("/api/query", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    def test_query_endpoint_includes_sources(self, test_client, test_data):
        """Query endpoint returns sources from search tools"""
        response = test_client.post("/api/query", json=test_data["sample_query_request"])

        assert response.status_code == 200
        data = response.json()
        assert len(data["sources"]) > 0
        assert data["sources"][0]["label"] == "Lesson 1: Introduction"
        assert data["sources"][0]["url"] == "https://example.com/lesson/1"

    def test_query_endpoint_error_handling(self, test_client, mock_rag_system):
        """Query endpoint handles errors gracefully"""
        # Mock the query method to raise an exception
        mock_rag_system.query = MagicMock(side_effect=ValueError("Test error"))

        response = test_client.post("/api/query", json={"query": "Test query"})

        assert response.status_code == 500
        assert "detail" in response.json()

    def test_query_endpoint_invalid_request(self, test_client):
        """Query endpoint rejects requests without required fields"""
        response = test_client.post("/api/query", json={})

        # Pydantic validation error
        assert response.status_code == 422

    def test_query_endpoint_updates_conversation_history(self, test_client, test_data, mock_rag_system):
        """Query endpoint stores user query in session history"""
        session_id = mock_rag_system.session_manager.create_session()
        request_data = {"query": test_data["sample_query"], "session_id": session_id}

        test_client.post("/api/query", json=request_data)

        # Verify conversation history was updated
        history = mock_rag_system.session_manager.get_conversation_history(session_id)
        assert history is not None
        assert test_data["sample_query"] in history


class TestCoursesEndpoint:
    """Tests for GET /api/courses endpoint"""

    def test_courses_endpoint_success(self, test_client):
        """Courses endpoint returns course statistics"""
        response = test_client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()
        assert "total_courses" in data
        assert "course_titles" in data

    def test_courses_endpoint_response_structure(self, test_client):
        """Courses endpoint returns correct response structure"""
        response = test_client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["total_courses"], int)
        assert isinstance(data["course_titles"], list)

    def test_courses_endpoint_initial_state(self, test_client, mock_rag_system):
        """Courses endpoint returns zero courses initially"""
        response = test_client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()
        assert data["total_courses"] == 0
        assert data["course_titles"] == []

    def test_courses_endpoint_error_handling(self, test_client, mock_rag_system):
        """Courses endpoint handles errors gracefully"""
        # Mock the analytics method to raise an exception
        mock_rag_system.get_course_analytics = MagicMock(
            side_effect=RuntimeError("Database error")
        )

        response = test_client.get("/api/courses")

        assert response.status_code == 500
        assert "detail" in response.json()

    def test_courses_endpoint_no_parameters(self, test_client):
        """Courses endpoint requires no query parameters"""
        response = test_client.get("/api/courses?extra_param=value")

        # Extra parameters should be ignored, endpoint should still work
        assert response.status_code == 200


class TestSessionEndpoint:
    """Tests for DELETE /api/session/{session_id} endpoint"""

    def test_clear_session_endpoint_success(self, test_client, mock_rag_system):
        """Clear session endpoint successfully clears conversation history"""
        # Create a session with some data
        session_id = mock_rag_system.session_manager.create_session()
        mock_rag_system.session_manager.add_exchange(
            session_id, "What is AI?", "AI is artificial intelligence."
        )

        # Clear the session
        response = test_client.delete(f"/api/session/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cleared"
        assert data["session_id"] == session_id

    def test_clear_session_endpoint_clears_history(self, test_client, mock_rag_system):
        """Clear session endpoint removes conversation history"""
        session_id = mock_rag_system.session_manager.create_session()
        mock_rag_system.session_manager.add_exchange(
            session_id, "What is AI?", "AI is artificial intelligence."
        )

        # Verify history exists
        history_before = mock_rag_system.session_manager.get_conversation_history(
            session_id
        )
        assert history_before is not None

        # Clear the session
        test_client.delete(f"/api/session/{session_id}")

        # Verify history is cleared
        history_after = mock_rag_system.session_manager.get_conversation_history(
            session_id
        )
        assert history_after is None

    def test_clear_session_endpoint_nonexistent_session(self, test_client):
        """Clear session endpoint handles nonexistent session gracefully"""
        response = test_client.delete("/api/session/nonexistent_session_123")

        # Should succeed even for nonexistent sessions
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cleared"
        assert data["session_id"] == "nonexistent_session_123"

    def test_clear_session_endpoint_response_structure(self, test_client, mock_rag_system):
        """Clear session endpoint returns correct response structure"""
        session_id = mock_rag_system.session_manager.create_session()

        response = test_client.delete(f"/api/session/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "session_id" in data


class TestEndpointIntegration:
    """Integration tests across multiple endpoints"""

    def test_session_lifecycle(self, test_client, mock_rag_system, test_data):
        """Complete session lifecycle: create, query, clear"""
        # Create a new session via query
        response1 = test_client.post("/api/query", json=test_data["sample_query_request"])
        assert response1.status_code == 200
        session_id = response1.json()["session_id"]

        # Use the same session for another query
        request_data = {
            "query": "Follow-up question",
            "session_id": session_id,
        }
        response2 = test_client.post("/api/query", json=request_data)
        assert response2.status_code == 200
        assert response2.json()["session_id"] == session_id

        # Clear the session
        response3 = test_client.delete(f"/api/session/{session_id}")
        assert response3.status_code == 200

    def test_multiple_sessions_isolation(self, test_client, mock_rag_system, test_data):
        """Multiple sessions maintain separate conversation histories"""
        # Create first session
        response1 = test_client.post(
            "/api/query",
            json={"query": "Question 1", "session_id": None},
        )
        session1 = response1.json()["session_id"]

        # Create second session
        response2 = test_client.post(
            "/api/query",
            json={"query": "Question 2", "session_id": None},
        )
        session2 = response2.json()["session_id"]

        # Verify sessions are different
        assert session1 != session2

        # Verify histories are separate
        history1 = mock_rag_system.session_manager.get_conversation_history(session1)
        history2 = mock_rag_system.session_manager.get_conversation_history(session2)

        assert history1 != history2
        assert "Question 1" in history1
        assert "Question 2" in history2

    def test_courses_endpoint_consistent_state(self, test_client):
        """Courses endpoint returns consistent data on multiple calls"""
        response1 = test_client.get("/api/courses")
        response2 = test_client.get("/api/courses")

        data1 = response1.json()
        data2 = response2.json()

        assert data1["total_courses"] == data2["total_courses"]
        assert data1["course_titles"] == data2["course_titles"]
