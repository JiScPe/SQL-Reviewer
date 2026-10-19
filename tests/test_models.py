import pytest
from models import Finding, FindingStatus, Severity


def test_finding_creation():
    finding = Finding(
        severity="error",
        file="SQL_STH260804018.sql",
        line=87,
        title="Missing message_locale en_US",
        description="message_key 'MSG.ORDER.HOLD' has only th_TH.",
        recommendation="Add an INSERT for MSG.ORDER.HOLD with message_locale = 'en_US'.",
    )
    assert finding.severity == "error"
    assert finding.file == "SQL_STH260804018.sql"
    assert finding.line == 87
    assert finding.title == "Missing message_locale en_US"
    assert finding.status == "pending"
    assert finding.id is not None
    assert len(finding.id) == 16


def test_finding_id_deterministic():
    f1 = Finding(
        severity="error",
        file="SQL_STH260804018.sql",
        line=87,
        title="Missing message_locale en_US",
        description="desc",
        recommendation="rec",
    )
    f2 = Finding(
        severity="error",
        file="SQL_STH260804018.sql",
        line=87,
        title="Missing message_locale en_US",
        description="different desc",
        recommendation="different rec",
    )
    assert f1.id == f2.id


def test_finding_to_dict():
    finding = Finding(
        severity="warning",
        file="test.sql",
        line=10,
        title="Test warning",
        description="Description",
        recommendation="Recommendation",
        status="approved",
    )
    data = finding.to_dict()
    assert data["severity"] == "warning"
    assert data["status"] == "approved"
    assert data["id"] == finding.id


def test_finding_from_dict():
    data = {
        "id": "abc123",
        "severity": "info",
        "file": "test.sql",
        "line": 5,
        "title": "Info",
        "description": "Desc",
        "recommendation": "Rec",
        "status": "rejected",
    }
    finding = Finding.from_dict(data)
    assert finding.id == "abc123"
    assert finding.severity == "info"
    assert finding.status == "rejected"