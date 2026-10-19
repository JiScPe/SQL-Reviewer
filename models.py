from dataclasses import dataclass, field
from typing import Literal, Optional
import hashlib


Severity = Literal["error", "warning", "info"]
FindingStatus = Literal["pending", "approved", "edited", "rejected"]


@dataclass
class Finding:
    severity: Severity
    file: str
    line: int
    title: str
    description: str
    recommendation: str
    status: FindingStatus = "pending"
    id: str = field(init=False)

    def __post_init__(self):
        self.id = self._compute_id()

    def _compute_id(self) -> str:
        content = f"{self.file}:{self.line}:{self.title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        finding = cls(
            severity=data["severity"],
            file=data["file"],
            line=data["line"],
            title=data["title"],
            description=data["description"],
            recommendation=data["recommendation"],
            status=data.get("status", "pending"),
        )
        finding.id = data.get("id", finding.id)
        return finding


@dataclass
class RunResult:
    run_id: int
    deploy_date: str
    findings: list[Finding]
    state: str