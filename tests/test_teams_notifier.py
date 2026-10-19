import pytest
from unittest.mock import Mock, patch, MagicMock
import os
import httpx

from teams_notifier import TeamsNotifier
from models import Finding


@pytest.fixture
def mock_env():
    os.environ["TEAMS_WEBHOOK_URL"] = "https://test.webhook.url"
    yield
    del os.environ["TEAMS_WEBHOOK_URL"]


@pytest.fixture
def mock_httpx_client():
    with patch('teams_notifier.httpx.Client') as mock_client_class:
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        yield client_instance


def test_teams_notifier_init(mock_env):
    notifier = TeamsNotifier()
    assert notifier.webhook_url == "https://test.webhook.url"


def test_teams_notifier_post_finding(mock_env, mock_httpx_client):
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post.return_value = mock_response
    
    notifier = TeamsNotifier()
    
    with patch('teams_notifier.issue_posted', return_value=False), \
         patch('teams_notifier.mark_issue_posted') as mock_mark:
        
        finding = Finding(
            severity="error",
            file="SQL_STH260804018.sql",
            line=10,
            title="Missing message_locale en_US",
            description="message_key 'MSG.TEST' has only th_TH.",
            recommendation="Add an INSERT for MSG.TEST with message_locale = 'en_US'.",
            status="approved"
        )
        
        notifier.post([finding], {"run_id": 1, "deploy_date": "10.13"})
        
        # Verify HTTP call
        mock_httpx_client.post.assert_called_once()
        call_args = mock_httpx_client.post.call_args
        assert call_args[0][0] == "https://test.webhook.url"
        card = call_args[1]["json"]
        assert card["type"] == "message"
        assert "attachments" in card
        assert card["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
        
        # Verify deduplication
        mock_mark.assert_called_once()


def test_teams_notifier_post_no_issues(mock_env, mock_httpx_client):
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post.return_value = mock_response
    
    notifier = TeamsNotifier()
    
    notifier.post([], {"run_id": 1, "deploy_date": "10.13", "file": "test.sql"})
    
    mock_httpx_client.post.assert_called_once()
    card = mock_httpx_client.post.call_args[1]["json"]
    assert "✅" in card["attachments"][0]["content"]["body"][0]["text"]


def test_teams_notifier_deduplication(mock_env, mock_httpx_client):
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post.return_value = mock_response
    
    notifier = TeamsNotifier()
    
    with patch('teams_notifier.issue_posted', return_value=True), \
         patch('teams_notifier.mark_issue_posted') as mock_mark:
        
        finding = Finding(
            severity="error",
            file="test.sql",
            line=1,
            title="Test",
            description="Desc",
            recommendation="Rec",
            status="approved"
        )
        
        notifier.post([finding], {"run_id": 1})
        
        # Should not call HTTP if already posted
        mock_httpx_client.post.assert_not_called()
        mock_mark.assert_not_called()


def test_teams_notifier_retry_on_error(mock_env, mock_httpx_client):
    mock_httpx_client.post.side_effect = [
        httpx.HTTPError("Network error"),
        Mock(raise_for_status=Mock())
    ]
    
    notifier = TeamsNotifier()
    
    with patch('teams_notifier.issue_posted', return_value=False), \
         patch('teams_notifier.mark_issue_posted'):
        
        finding = Finding(
            severity="error",
            file="test.sql",
            line=1,
            title="Test",
            description="Desc",
            recommendation="Rec",
            status="approved"
        )
        
        notifier.post([finding], {"run_id": 1})
        
        # Should retry and succeed
        assert mock_httpx_client.post.call_count == 2


def test_teams_notifier_max_retries_exceeded(mock_env, mock_httpx_client):
    mock_httpx_client.post.side_effect = httpx.HTTPError("Persistent error")
    
    notifier = TeamsNotifier()
    
    with patch('teams_notifier.issue_posted', return_value=False), \
         patch('teams_notifier.mark_issue_posted'):
        
        finding = Finding(
            severity="error",
            file="test.sql",
            line=1,
            title="Test",
            description="Desc",
            recommendation="Rec",
            status="approved"
        )
        
        with pytest.raises(httpx.HTTPError):
            notifier.post([finding], {"run_id": 1})
        
        # Should try max_retries times (default 3)
        assert mock_httpx_client.post.call_count == 3


def test_teams_notifier_pacing_delay(mock_env, mock_httpx_client):
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_httpx_client.post.return_value = mock_response
    
    notifier = TeamsNotifier()
    
    with patch('teams_notifier.issue_posted', return_value=False), \
         patch('teams_notifier.mark_issue_posted'), \
         patch('teams_notifier.time.sleep') as mock_sleep:
        
        finding = Finding(
            severity="error",
            file="test.sql",
            line=1,
            title="Test",
            description="Desc",
            recommendation="Rec",
            status="approved"
        )
        
        notifier.post([finding], {"run_id": 1})
        
        # Should sleep for pacing delay
        mock_sleep.assert_called()