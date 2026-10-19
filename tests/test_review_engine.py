import pytest
from review_engine import review_sql_file


def test_review_engine_syntax_errors():
    findings = review_sql_file('samples/SQL_sample.sql')
    syntax_errors = [f for f in findings if f.title == "PostgreSQL syntax error"]
    assert len(syntax_errors) >= 2  # merged statements + unbalanced parens


def test_review_engine_missing_locale():
    findings = review_sql_file('samples/SQL_sample.sql')
    locale_errors = [f for f in findings if f.title == "Missing message_locale column"]
    assert len(locale_errors) == 1
    assert locale_errors[0].file == "SQL_sample.sql"


def test_review_engine_complex_insert_warning():
    findings = review_sql_file('samples/SQL_sample.sql')
    complex_warnings = [f for f in findings if f.title == "Complex INSERT into ims_message requires manual check"]
    assert len(complex_warnings) == 1


def test_review_engine_embedded_sql_checks():
    findings = review_sql_file('samples/SQL_sample.sql')
    embedded_errors = [f for f in findings if "Embedded SQL" in f.title or "table alias" in f.title or "column reference" in f.title]
    assert len(embedded_errors) >= 3  # undefined alias bu (2x), 3-part reference, undefined alias bu (2x)


def test_review_engine_smart_quote_warning():
    findings = review_sql_file('samples/SQL_sample.sql')
    smart_quote_warnings = [f for f in findings if f.title == "Typographic or invisible characters detected"]
    assert len(smart_quote_warnings) >= 1


def test_review_engine_valid_file():
    findings = review_sql_file('samples/SQL_synthetic_test.sql')
    # Should have no errors, only info "No issues found"
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    assert len(errors) == 0
    assert len(warnings) == 0
    info_findings = [f for f in findings if f.severity == "info"]
    assert len(info_findings) >= 1
    assert info_findings[0].title == "No issues found"