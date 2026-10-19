import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from ui.main import app
from models import Finding


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_get(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "SQL Review Agent Dashboard" in response.text


def test_start_run(client):
    with patch('ui.main.run_pipeline') as mock_run:
        mock_result = Mock()
        mock_result.run_id = 1
        mock_result.deploy_date = "10.13"
        mock_result.state = "Waiting for review"
        mock_result.sql_files = [Mock(filename="test.sql")]
        mock_result.findings = []
        mock_result.error = None
        mock_run.return_value = mock_result
        
        response = client.post("/api/run?deploy_date=10.13")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == 1
        assert data["deploy_date"] == "10.13"


def test_get_run_info(client):
    with patch('ui.main.get_run') as mock_get:
        mock_get.return_value = {"id": 1, "deploy_date": "10.13", "state": "Done"}
        
        response = client.get("/api/run/1")
        assert response.status_code == 200
        assert response.json()["deploy_date"] == "10.13"


def test_stream_events(client):
    with patch('ui.main.get_events') as mock_events, \
         patch('ui.main.get_run') as mock_get_run:
        mock_events.return_value = [
            {"id": 1, "step": "Opening sheet", "status": "started", "message": "Starting...", "timestamp": "2024-01-01 10:00:00"},
            {"id": 2, "step": "Opening sheet", "status": "completed", "message": "Done", "timestamp": "2024-01-01 10:00:05"},
        ]
        mock_get_run.return_value = {"id": 1, "state": "Done"}
        
        # Just test that the endpoint returns the right content type without consuming the stream
        response = client.get("/api/run/1/events")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


def test_approve_finding(client):
    response = client.post("/api/findings/test-id/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_reject_finding(client):
    response = client.post("/api/findings/test-id/reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_edit_finding(client):
    response = client.post("/api/findings/test-id/edit", json={"title": "New title"})
    assert response.status_code == 200
    assert response.json()["status"] == "edited"


def test_dispatch_findings(client):
    with patch('ui.main.TeamsNotifier') as mock_notifier:
        mock_instance = Mock()
        mock_notifier.return_value = mock_instance
        
        response = client.post("/api/run/1/dispatch")
        assert response.status_code == 200
        assert response.json()["status"] == "dispatched"