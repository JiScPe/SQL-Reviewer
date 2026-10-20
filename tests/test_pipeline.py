import pytest
from unittest.mock import Mock, patch, MagicMock
from pipeline import ReviewPipeline, run_pipeline
from models import Finding
from sheet_fetcher import SQLFile
from database import init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def mock_sheet_fetcher():
    with patch('pipeline.SheetFetcher') as mock:
        fetcher_instance = Mock()
        fetcher_instance.fetch.return_value = [
            SQLFile(sr_number="STH260804018", content="SELECT 1;", filename="SQL_STH260804018.sql"),
            SQLFile(sr_number="STH260904020", content="INSERT INTO ims_message (message_key, message_locale, message_text) VALUES ('MSG.TEST', 'th_TH', 'test');", filename="SQL_STH260904020.sql"),
        ]
        mock.return_value = fetcher_instance
        yield fetcher_instance


@pytest.fixture
def mock_review_engine():
    with patch('pipeline.ReviewEngine') as mock:
        engine_instance = Mock()
        engine_instance.review_file.side_effect = [
            [Finding(severity="info", file="SQL_STH260804018.sql", line=0, title="No issues found", description="All checks passed.", recommendation="No action required.")],
            [Finding(severity="error", file="SQL_STH260904020.sql", line=1, title="Missing message_locale en_US", description="message_key 'MSG.TEST' has only th_TH.", recommendation="Add an INSERT for MSG.TEST with message_locale = 'en_US'.")]
        ]
        mock.return_value = engine_instance
        yield engine_instance


@pytest.fixture
def mock_explainer():
    with patch('pipeline.FindingExplainer') as mock:
        explainer_instance = Mock()
        explainer_instance.explain.side_effect = lambda findings: findings
        mock.return_value = explainer_instance
        yield explainer_instance


def test_pipeline_run_success(mock_sheet_fetcher, mock_review_engine, mock_explainer):
    result = run_pipeline("10.13")
    
    assert result.run_id is not None
    assert result.deploy_date == "10.13"
    assert result.state == "Waiting for review"
    assert len(result.sql_files) == 2
    assert len(result.findings) == 2
    assert result.error is None


def test_pipeline_run_empty_deploy(mock_sheet_fetcher, mock_review_engine, mock_explainer):
    mock_sheet_fetcher.fetch.return_value = []
    
    result = run_pipeline("10.13")
    
    assert result.state == "Done"
    assert len(result.sql_files) == 0
    assert len(result.findings) == 0


def test_pipeline_run_error(mock_sheet_fetcher, mock_review_engine, mock_explainer):
    mock_sheet_fetcher.fetch.side_effect = Exception("Browser error")
    
    result = run_pipeline("10.13")
    
    assert result.state == "Failed"
    assert result.error == "Browser error"


def test_pipeline_llm_disabled():
    from config import get_config
    config = get_config()
    original_llm_enabled = config.llm_enabled
    config.llm_enabled = False
    
    try:
        with patch('pipeline.SheetFetcher') as mock_sf, \
             patch('pipeline.ReviewEngine') as mock_re, \
             patch('pipeline.FindingExplainer') as mock_ex:
            
            mock_sf_instance = Mock()
            mock_sf_instance.fetch.return_value = [
                SQLFile(sr_number="STH260804018", content="SELECT 1;", filename="SQL_STH260804018.sql")
            ]
            mock_sf.return_value = mock_sf_instance
            
            mock_re_instance = Mock()
            mock_re_instance.review_file.return_value = [
                Finding(severity="info", file="test.sql", line=0, title="No issues found", description="All checks passed.", recommendation="No action required.")
            ]
            mock_re.return_value = mock_re_instance
            
            mock_ex_instance = Mock()
            mock_ex_instance.explain.side_effect = lambda f: f
            mock_ex.return_value = mock_ex_instance
            
            result = run_pipeline("10.13")
            
            # Explainer should not be called when llm_enabled is False
            mock_ex_instance.explain.assert_not_called()
    finally:
        config.llm_enabled = original_llm_enabled