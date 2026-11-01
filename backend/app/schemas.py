from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

Severity = Literal["Critical", "High", "Medium", "Low", "Informational"]
Language = Literal["python", "javascript", "typescript", "java", "cpp"]
MAX_CODE = 100_000


class AIFinding(BaseModel):
    category: str = Field(max_length=100)
    severity: Severity
    title: str = Field(max_length=300)
    description: str = Field(max_length=4000)
    impact: str = Field("", max_length=2000)
    file_path: Optional[str] = None
    line_start: Optional[int] = Field(None, ge=1)
    line_end: Optional[int] = Field(None, ge=1)
    remediation: str = Field("", max_length=4000)
    corrected_code: Optional[str] = Field(None, max_length=8000)
    confidence: Literal["high", "medium", "low"] = "medium"
    # "confirmed": the defect is demonstrable from the code shown; "possible": plausible concern.
    certainty: Literal["confirmed", "possible"] = "possible"
    # Verbatim copy of the offending line(s); verified against the code before it is kept and stored.
    evidence: Optional[str] = Field(None, max_length=500)


class AIResult(BaseModel):
    findings: list[AIFinding]


class Finding(AIFinding):
    id: str
    source: Literal["ai", "static_analysis"]
    analyzer: Optional[str] = None
    rule_id: Optional[str] = None


class ReviewRequest(BaseModel):
    code: str = Field(min_length=1, max_length=MAX_CODE)
    language: Language

    @field_validator("code")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("code must not be blank")
        return v


class ReviewOut(BaseModel):
    id: str
    created_at: datetime
    language: str
    provider: str
    is_mock: bool
    analyzers: dict[str, str]
    ai_error: Optional[str] = None
    source_kind: str = "manual"
    repo: Optional[str] = None
    pr_number: Optional[int] = None
    findings: list[Finding]
