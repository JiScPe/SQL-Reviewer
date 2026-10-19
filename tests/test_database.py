import pytest
import os
from database import init_db, create_run, update_run_state, add_event, get_events, get_run, issue_posted, mark_issue_posted


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists("events.db"):
        os.remove("events.db")
    init_db()
    yield
    if os.path.exists("events.db"):
        os.remove("events.db")


def test_init_db_creates_tables():
    run_id = create_run("10.13")
    assert run_id == 1
    run = get_run(run_id)
    assert run["deploy_date"] == "10.13"
    assert run["state"] == "Queued"


def test_update_run_state():
    run_id = create_run("10.13")
    update_run_state(run_id, "Reviewing")
    run = get_run(run_id)
    assert run["state"] == "Reviewing"


def test_add_and_get_events():
    run_id = create_run("10.13")
    add_event(run_id, "Opening sheet", "started", "Opening kdocs sheet")
    add_event(run_id, "Opening sheet", "completed", "Sheet exported")
    events = get_events(run_id)
    assert len(events) == 2
    assert events[0]["step"] == "Opening sheet"
    assert events[0]["status"] == "started"
    assert events[1]["status"] == "completed"


def test_issue_posted_deduplication():
    run_id = create_run("10.13")
    issue_hash = "abc123def456"
    assert not issue_posted(issue_hash, run_id)
    mark_issue_posted(issue_hash, run_id)
    assert issue_posted(issue_hash, run_id)
    mark_issue_posted(issue_hash, run_id)


def test_issue_posted_per_run():
    run_id1 = create_run("10.13")
    run_id2 = create_run("10.14")
    issue_hash = "abc123def456"
    mark_issue_posted(issue_hash, run_id1)
    assert issue_posted(issue_hash, run_id1)
    assert not issue_posted(issue_hash, run_id2)