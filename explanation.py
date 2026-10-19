import json
import time
import hashlib
from typing import List, Dict
from functools import lru_cache

import httpx

from models import Finding
from config import get_config


class FindingExplainer:
    def __init__(self):
        self.config = get_config()
        self.client = httpx.Client(timeout=self.config.llm_timeout_seconds)
        self._cache: Dict[str, tuple[str, str]] = {}

    def explain(self, findings: List[Finding]) -> List[Finding]:
        """Polish finding descriptions using local LLM."""
        if not self.config.llm_enabled:
            return findings
        
        explained_findings = []
        for finding in findings:
            if finding.severity in ("error", "warning"):
                polished = self._explain_finding(finding)
                explained_findings.append(Finding(
                    severity=finding.severity,
                    file=finding.file,
                    line=finding.line,
                    title=finding.title,
                    description=polished[0],
                    recommendation=polished[1],
                    status=finding.status,
                ))
            else:
                explained_findings.append(finding)
        
        return explained_findings

    def _explain_finding(self, finding: Finding) -> tuple[str, str]:
        """Explain a single finding using LLM."""
        cache_key = f"{finding.title}:{finding.severity}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        prompt = self._build_prompt(finding)
        
        try:
            response = self.client.post(
                f"{self.config.ollama_url}/api/generate",
                json={
                    "model": "qwen2.5-coder:3b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 200
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            polished_text = result.get("response", "").strip()
            
            # Parse the response (expecting JSON with description and recommendation)
            try:
                parsed = json.loads(polished_text)
                description = parsed.get("description", finding.description)
                recommendation = parsed.get("recommendation", finding.recommendation)
            except json.JSONDecodeError:
                # Fallback to original text if response is not valid JSON
                description = finding.description
                recommendation = finding.recommendation
            
            self._cache[cache_key] = (description, recommendation)
            return description, recommendation
            
        except Exception:
            # Fallback to original text
            return finding.description, finding.recommendation

    def _build_prompt(self, finding: Finding) -> str:
        return f"""You are a SQL code reviewer. Rewrite the following finding in clear, concise technical language.

Finding:
- Severity: {finding.severity}
- Title: {finding.title}
- Description: {finding.description}
- Recommendation: {finding.recommendation}

Return a JSON object with two fields:
{{
  "description": "Clear explanation of the issue (max 2 sentences)",
  "recommendation": "Specific actionable fix (max 2 sentences)"
}}

Do not include any other text."""

    def clear_cache(self):
        self._cache.clear()