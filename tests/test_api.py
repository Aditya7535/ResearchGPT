"""
Unit tests for FastAPI endpoints in app/main.py.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check_endpoint(client):
    """Test that /api/health responds with status healthy."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "llm_provider" in data


def test_unsupported_file_upload(client):
    """Test that uploading unsupported file types returns 400."""
    response = client.post(
        "/api/ingest",
        files={"file": ("malicious.exe", b"binary content", "application/octet-stream")}
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


@patch("app.agents.interview.generate_interview_questions")
def test_interview_generate_endpoint(mock_generate, client):
    """Test /api/interview/generate endpoint."""
    mock_generate.return_value = [
        {"question_id": "q1", "question": "What sample size was used?"}
    ]

    response = client.post(
        "/api/interview/generate",
        json={"section_name": "Methods", "domain": "Quantum Computing"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["section_name"] == "Methods"
    assert len(data["questions"]) == 1
    assert data["questions"][0]["question_id"] == "q1"


@patch("app.agents.interview.synthesize_interview_section")
def test_interview_answer_endpoint(mock_synthesize, client):
    """Test /api/interview/answer endpoint."""
    mock_synthesize.return_value = {
        "section_name": "Methods",
        "prose": "We tested 50 qubits.",
        "tagged_sentences": [{"text": "We tested 50 qubits.", "source": "user-interview"}],
        "open_gaps": [],
        "qna_history": [{"question_id": "q1", "answer": "50 qubits"}]
    }

    response = client.post(
        "/api/interview/answer",
        json={
            "section_name": "Methods",
            "qna_pairs": [{"question_id": "q1", "answer": "50 qubits"}],
            "partial_content": ""
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["section_name"] == "Methods"
    assert "50 qubits" in data["prose"]
