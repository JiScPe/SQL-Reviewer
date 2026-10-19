from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

from models import Finding, RunResult
from database import create_run, update_run_state, add_event, get_run
from config import get_config
from review_engine import ReviewEngine
from sheet_fetcher import SheetFetcher, SQLFile
from explanation import FindingExplainer


@dataclass
class PipelineResult:
    run_id: int
    deploy_date: str
    sql_files: List[SQLFile]
    findings: List[Finding]
    state: str
    error: Optional[str] = None


class ReviewPipeline:
    def __init__(self):
        self.config = get_config()
        self.review_engine = ReviewEngine()
        self.sheet_fetcher = SheetFetcher()
        self.explainer = FindingExplainer()

    def run(self, deploy_date: str) -> PipelineResult:
        """Execute the full review pipeline for a deploy date."""
        run_id = create_run(deploy_date)
        
        try:
            # Step 1: Fetch SQL files from kdocs
            update_run_state(run_id, "Opening sheet")
            add_event(run_id, "Opening sheet", "started", f"Fetching SQL files for deploy {deploy_date}")
            
            sql_files = self.sheet_fetcher.fetch(deploy_date, run_id)
            
            if not sql_files:
                update_run_state(run_id, "Done")
                add_event(run_id, "Done", "completed", "No SQL files in this deploy")
                return PipelineResult(
                    run_id=run_id,
                    deploy_date=deploy_date,
                    sql_files=[],
                    findings=[],
                    state="Done"
                )
            
            add_event(run_id, "Opening sheet", "completed", f"Fetched {len(sql_files)} SQL file(s)")
            
            # Step 2: Review each SQL file
            update_run_state(run_id, "Reviewing")
            add_event(run_id, "Reviewing", "started", f"Reviewing {len(sql_files)} SQL file(s)")
            
            all_findings = []
            for sql_file in sql_files:
                add_event(run_id, "Reviewing", "progress", f"Reviewing {sql_file.filename}")
                findings = self.review_engine.review_file(sql_file.content)
                # Tag findings with file info
                for finding in findings:
                    finding.file = sql_file.filename
                all_findings.extend(findings)
            
            add_event(run_id, "Reviewing", "completed", f"Found {len(all_findings)} issue(s)")
            
            # Step 3: Explain findings with LLM (if enabled)
            if self.config.llm_enabled and all_findings:
                update_run_state(run_id, "Explaining")
                add_event(run_id, "Explaining", "started", "Polishing findings with local LLM")
                all_findings = self.explainer.explain(all_findings)
                add_event(run_id, "Explaining", "completed", "LLM explanation complete")
            
            # Step 4: Wait for human review
            update_run_state(run_id, "Waiting for review")
            add_event(run_id, "Waiting for review", "started", "Awaiting human approval")
            
            # Store findings for review gate (in practice, this would be in the database)
            # For now, return the result for the UI to handle
            return PipelineResult(
                run_id=run_id,
                deploy_date=deploy_date,
                sql_files=sql_files,
                findings=all_findings,
                state="Waiting for review"
            )
            
        except Exception as e:
            update_run_state(run_id, "Failed")
            add_event(run_id, "Failed", "error", str(e))
            return PipelineResult(
                run_id=run_id,
                deploy_date=deploy_date,
                sql_files=[],
                findings=[],
                state="Failed",
                error=str(e)
            )


def run_pipeline(deploy_date: str) -> PipelineResult:
    pipeline = ReviewPipeline()
    return pipeline.run(deploy_date)