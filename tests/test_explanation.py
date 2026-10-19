import pytest
from unittest.mock import Mock, patch, MagicMock
from explanation import FindingExplainer
from models import Finding
from config import get_config


@pytest.fixture
def mock_httpx_client():
    with patch('explanation.httpx.Client') as mock_client_class:
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        yield client_instance


def test_explainer_disabled():
    config = get_config()
    original_enabled = config.llm_enabled
    config.llm_enabled = False
    
    try:
        explainer = FindingExplainer()
        findings = [
            Finding(severity="error", file="test.sql", line=1, title="Test", description="Desc", recommendation="Rec")
        ]
        result = explainer.explain(findings)
        assert result == findings
    finally:
        config.llm_enabled = original_enabled


def test_explainer_only_errors_warnings(mock_httpx_client):
    config = get_config()
    original_enabled = config.llm_enabled
    config.llm_enabled = True
    
    try:
        # Mock successful LLM response
        mock_response = Mock()
        mock_response.json.return_value = {"response": '{"description": "Polished desc", "recommendation": "Polished rec"}'}
        mock_response.raise_for_status = Mock()
        mock_httpx_client.post.return_value = mock_response
        
        explainer = FindingExplainer()
        findings = [
            Finding(severity="error", file="test.sql", line=1, title="Test Error", description="Desc", recommendation="Rec"),
            Finding(severity="warning", file="test.sql", line=2, title="Test Warning", description="Desc", recommendation="Rec"),
            Finding(severity="info", file="test.sql", line=3, title="Test Info", description="Desc", recommendation="Rec"),
        ]
        result = explainer.explain(findings)
        
        # Should call LLM for error and warning only (2 calls)
        assert mock_httpx_client.post.call_count == 2
        
        # Info finding should be unchanged
        info_finding = [f for f in result if f.severity == "info"][0]
        assert info_finding.description == "Desc"
    finally:
        config.llm_enabled = original_enabled


def test_explainer_caching(mock_httpx_client):
    config = get_config()
    original_enabled = config.llm_enabled
    config.llm_enabled = True
    
    try:
        mock_response = Mock()
        mock_response.json.return_value = {"response": '{"description": "Polished desc", "recommendation": "Polished rec"}'}
        mock_response.raise_for_status = Mock()
        mock_httpx_client.post.return_value = mock_response
        
        explainer = FindingExplainer()
        findings = [
            Finding(severity="error", file="test.sql", line=1, title="Same Title", description="Desc", recommendation="Rec"),
            Finding(severity="error", file="test2.sql", line=1, title="Same Title", description="Desc2", recommendation="Rec2"),
        ]
        result = explainer.explain(findings)
        
        # Should only call LLM once due to caching
        assert mock_httpx_client.post.call_count == 1
    finally:
        config.llm_enabled = original_enabled


def test_explainer_timeout_fallback(mock_httpx_client):
    config = get_config()
    original_enabled = config.llm_enabled
    config.llm_enabled = True
    
    try:
        import httpx
        mock_httpx_client.post.side_effect = httpx.TimeoutException("Timeout")
        
        explainer = FindingExplainer()
        findings = [
            Finding(severity="error", file="test.sql", line=1, title="Test", description="Original desc", recommendation="Original rec")
        ]
        result = explainer.explain(findings)
        
        # Should fall back to original text
        assert result[0].description == "Original desc"
        assert result[0].recommendation == "Original rec"
    finally:
        config.llm_enabled = original_enabled


def test_explainer_invalid_json_fallback(mock_httpx_client):
    config = get_config()
    original_enabled = config.llm_enabled
    config.llm_enabled = True
    
    try:
        mock_response = Mock()
        mock_response.json.return_value = {"response": "Not valid JSON"}
        mock_response.raise_for_status = Mock()
        mock_httpx_client.post.return_value = mock_response
        
        explainer = FindingExplainer()
        findings = [
            Finding(severity="error", file="test.sql", line=1, title="Test", description="Original desc", recommendation="Original rec")
        ]
        result = explainer.explain(findings)
        
        # Should fall back to original text when JSON parsing fails
        assert result[0].description == "Original desc"
    finally:
        config.llm_enabled = original_enabled