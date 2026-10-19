import os
import time
import hashlib
import httpx
from typing import List
from pathlib import Path

from models import Finding
from database import get_db, issue_posted, mark_issue_posted
from config import get_config


class TeamsNotifier:
    def __init__(self):
        self.config = get_config()
        self.webhook_url = os.getenv(self.config.teams_webhook_url_env)
        if not self.webhook_url:
            raise ValueError(f"TEAMS_WEBHOOK_URL environment variable not set")
        self.client = httpx.Client(timeout=30.0)

    def post(self, findings: List[Finding], run_metadata: dict):
        """Post findings to Teams as individual Adaptive Cards."""
        if not findings:
            self._post_no_issues(run_metadata)
            return
        
        # Group by file for clean file messages
        by_file = {}
        for finding in findings:
            if finding.status not in ("approved", "edited"):
                continue
            if finding.file not in by_file:
                by_file[finding.file] = []
            by_file[finding.file].append(finding)
        
        for file_name, file_findings in by_file.items():
            if not file_findings:
                self._post_no_issues({**run_metadata, "file": file_name})
                continue
            
            for finding in file_findings:
                self._post_finding(finding, run_metadata)

    def _post_finding(self, finding: Finding, run_metadata: dict):
        """Post a single finding as an Adaptive Card."""
        issue_id = finding.id
        
        # Check deduplication
        if issue_posted(issue_id, run_metadata.get("run_id", 0)):
            return
        
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(finding.severity, "ℹ️")
        
        card = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"{icon} Line {finding.line}: {finding.file} - {finding.title}",
                            "weight": "Bolder",
                            "size": "Medium",
                            "wrap": True
                        },
                        {
                            "type": "TextBlock",
                            "text": finding.description,
                            "wrap": True,
                            "spacing": "Medium"
                        },
                        {
                            "type": "TextBlock",
                            "text": finding.recommendation,
                            "wrap": True,
                            "spacing": "Medium",
                            "color": "Accent"
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "SR/Deploy", "value": run_metadata.get("deploy_date", "N/A")},
                                {"title": "Issue ID", "value": issue_id},
                                {"title": "Severity", "value": finding.severity.capitalize()}
                            ],
                            "spacing": "Medium"
                        }
                    ]
                }
            }]
        }
        
        self._send_with_retry(card)
        mark_issue_posted(issue_id, run_metadata.get("run_id", 0))

    def _post_no_issues(self, run_metadata: dict):
        """Post a 'No issues found' card for a clean file."""
        file_name = run_metadata.get("file", "unknown.sql")
        checks_run = run_metadata.get("checks_run", [
            "PostgreSQL syntax",
            "Message locale (en_US)",
            "Embedded SQL validation",
            "Encoding detection",
            "Smart quote detection"
        ])
        
        card = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"✅ {file_name} - No issues found",
                            "weight": "Bolder",
                            "size": "Medium",
                            "wrap": True,
                            "color": "Good"
                        },
                        {
                            "type": "TextBlock",
                            "text": "All checks passed successfully.",
                            "wrap": True,
                            "spacing": "Medium"
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Deploy Date", "value": run_metadata.get("deploy_date", "N/A")},
                                {"title": "Checks Run", "value": ", ".join(checks_run)}
                            ],
                            "spacing": "Medium"
                        }
                    ]
                }
            }]
        }
        
        self._send_with_retry(card)

    def _send_with_retry(self, card: dict):
        """Send card with pacing delay and retry logic."""
        time.sleep(self.config.teams_pacing_delay_ms / 1000.0)
        
        for attempt in range(self.config.teams_max_retries):
            try:
                response = self.client.post(self.webhook_url, json=card)
                response.raise_for_status()
                return
            except httpx.HTTPError as e:
                if attempt == self.config.teams_max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff