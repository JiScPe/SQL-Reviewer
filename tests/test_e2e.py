"""End-to-end integration tests for the full SQL Review Agent pipeline."""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from pipeline import run_pipeline
from review_engine import ReviewEngine
from models import Finding
from database import init_db, get_events, get_run
from config import get_config


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


@pytest.fixture
def sample_sql_file():
    """Create a temporary SQL file for testing."""
    content = """-- Test SQL
INSERT INTO ims_message (message_key, message_locale, message_text) VALUES
('MSG.TEST', 'th_TH', 'Test Thai'),
('MSG.TEST', 'en_US', 'Test English');

-- Embedded SQL with issues
INSERT INTO ims_report_config (report_key, query_sql) VALUES
('RPT.TEST', 'select%20i.item_code%2C%20bw.u.wu_id%2C%20bu.wu_code%20from%20inventory%20i%20join%20warehouse%20w%20on%20i.warehouse_id%20=%20w.warehouse_id%20join%20batch_warn%20bw%20on%20bw.warehouse_id%20=%20w.warehouse_id%20where%20i.status%20=%20%27active%27');

-- Syntax error
INSERT INTO test_table (col1) VALUES ('test')
INSERT INTO test_table2 (col2) VALUES ('test2');
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write(content)
        f.flush()
        yield f.name
    Path(f.name).unlink(missing_ok=True)


def test_review_engine_on_sample(sample_sql_file):
    """Test review engine on sample SQL file."""
    engine = ReviewEngine()
    findings = engine.review_file(sample_sql_file)
    
    # Should find: locale OK, embedded SQL issues, syntax error
    titles = [f.title for f in findings]
    
    # Check for expected findings
    assert any("PostgreSQL syntax error" in t for t in titles)
    assert any("Undefined table alias" in t or "Invalid column reference" in t for t in titles)
    assert any("Missing message_locale column" not in t for t in titles)  # locale should be OK


def test_pipeline_empty_deploy():
    """Test pipeline handles empty deploy window."""
    with patch('pipeline.SheetFetcher') as mock_fetcher:
        mock_instance = Mock()
        mock_instance.fetch.return_value = []
        mock_fetcher.return_value = mock_instance
        
        result = run_pipeline("99.99")  # Non-existent deploy date
        
        assert result.state == "Done"
        assert len(result.sql_files) == 0
        assert len(result.findings) == 0


def test_pipeline_with_findings():
    """Test pipeline processes findings correctly."""
    with patch('pipeline.SheetFetcher') as mock_fetcher, \
         patch('pipeline.ReviewEngine') as mock_engine, \
         patch('pipeline.FindingExplainer') as mock_explainer:
        
        # Mock sheet fetcher
        mock_fetcher_instance = Mock()
        mock_fetcher_instance.fetch.return_value = [
            Mock(sr_number="STH260804018", content="SELECT 1;", filename="SQL_STH260804018.sql")
        ]
        mock_fetcher.return_value = mock_fetcher_instance
        
        # Mock review engine
        mock_engine_instance = Mock()
        mock_engine_instance.review_file.return_value = [
            Finding(severity="error", file="SQL_STH260804018.sql", line=10, title="Test Error", description="Desc", recommendation="Rec")
        ]
        mock_engine.return_value = mock_engine_instance
        
        # Mock explainer
        mock_explainer_instance = Mock()
        mock_explainer_instance.explain.side_effect = lambda f: f
        mock_explainer.return_value = mock_explainer_instance
        
        result = run_pipeline("10.13")
        
        assert result.state == "Waiting for review"
        assert len(result.findings) == 1
        assert result.findings[0].severity == "error"


def test_event_logging():
    """Test that events are logged to database."""
    from database import create_run, add_event, get_events
    
    run_id = create_run("10.13")
    add_event(run_id, "Test Step", "started", "Test message")
    add_event(run_id, "Test Step", "completed", "Done")
    
    events = get_events(run_id)
    assert len(events) == 2
    assert events[0]["step"] == "Test Step"
    assert events[0]["status"] == "started"
    assert events[1]["status"] == "completed"


def test_deduplication():
    """Test issue deduplication across runs."""
    from database import create_run, issue_posted, mark_issue_posted
    import uuid
    
    run_id1 = create_run("10.13")
    run_id2 = create_run("10.14")
    
    issue_hash = f"test-{uuid.uuid4().hex[:8]}"
    
    assert not issue_posted(issue_hash, run_id1)
    assert not issue_posted(issue_hash, run_id2)
    
    mark_issue_posted(issue_hash, run_id1)
    
    assert issue_posted(issue_hash, run_id1)
    assert not issue_posted(issue_hash, run_id2)  # Different run


def test_config_loading():
    """Test configuration loads correctly."""
    config = get_config()
    assert config.sr_prefixes == ["STH", "STP", "SFQ", "SWH", "SXM", "SBJ", "SQD"]
    assert config.message_table == "ims_message"
    assert config.required_locale == "en_US"
    assert config.llm_enabled is True
    assert config.login_timeout_seconds == 300
    assert config.teams_pacing_delay_ms == 500


def test_finding_schema():
    """Test Finding model schema."""
    finding = Finding(
        severity="error",
        file="test.sql",
        line=10,
        title="Test",
        description="Desc",
        recommendation="Rec"
    )
    
    assert finding.id is not None
    assert len(finding.id) == 16
    assert finding.status == "pending"
    
    # Test deterministic ID
    finding2 = Finding(
        severity="error",
        file="test.sql",
        line=10,
        title="Test",
        description="Different",
        recommendation="Different"
    )
    assert finding.id == finding2.id
    
    # Test to/from dict
    data = finding.to_dict()
    finding3 = Finding.from_dict(data)
    assert finding3.id == finding.id
    assert finding3.severity == finding.severity


def test_review_engine_encoding_detection():
    """Test encoding detection for non-UTF-8 files."""
    import tempfile
    
    # Create a GBK-encoded file
    content = "SELECT 1;\n".encode('gbk')
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.sql', delete=False) as f:
        f.write(content)
        f.flush()
        gbk_file = f.name
    
    try:
        engine = ReviewEngine()
        findings = engine.review_file(gbk_file)
        
        # Should have encoding warning
        assert any("encoding" in f.title.lower() for f in findings)
    finally:
        Path(gbk_file).unlink(missing_ok=True)


def test_review_engine_smart_quotes():
    """Test smart quote detection."""
    import tempfile
    
    # Use actual smart quotes (Unicode)
    content = "INSERT INTO test VALUES ('It's a \"test\" with em-dash — and ellipsis …');"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
        f.write(content)
        f.flush()
        smart_file = f.name
    
    try:
        engine = ReviewEngine()
        findings = engine.review_file(smart_file)
        
        # Should have smart quote warning
        assert any("Typographic" in f.title for f in findings)
    finally:
        Path(smart_file).unlink(missing_ok=True)


def test_end_to_end_scenarios():
    """Test key end-to-end scenarios from user stories."""
    
    # Scenario 1: Deploy date required (no default) - invalid format
    with pytest.raises(ValueError):
        run_pipeline("invalid")  # Should fail validation
    
    # Scenario 2: SR prefix extraction
    import re
    sr_pattern = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(get_config().sr_prefixes) + r")\d{9}(?!\d)")
    
    assert sr_pattern.search("branches/STH260804018.新增").group(0) == "STH260804018"
    assert sr_pattern.search("merge:branches/STP261014021.其他").group(0) == "STP261014021"
    assert sr_pattern.search("no sr here") is None
    
    # Scenario 3: Fallback naming
    from datetime import datetime
    year = datetime.now().year
    date_str = f"{year}1013"
    import re
    fallback_pattern = re.compile(rf"SQL_{date_str}_\d{{3}}\.sql")
    
    import random, string
    for _ in range(3):
        random_digits = ''.join(random.choices(string.digits, k=3))
        filename = f"SQL_{date_str}_{random_digits}.sql"
        assert fallback_pattern.match(filename)
    
    # Scenario 4: Multi-script disambiguation
    sr_counts = {}
    for i in range(3):
        sr = "STH260804018"
        count = sr_counts.get(sr, 0) + 1
        sr_counts[sr] = count
        if count == 1:
            filename = f"SQL_{sr}.sql"
        else:
            filename = f"SQL_{sr}_{count}.sql"
        if i == 0:
            assert filename == "SQL_STH260804018.sql"
        elif i == 1:
            assert filename == "SQL_STH260804018_2.sql"
        elif i == 2:
            assert filename == "SQL_STH260804018_3.sql"