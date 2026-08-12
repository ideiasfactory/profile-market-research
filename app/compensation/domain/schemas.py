from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class AllocationModel(str, Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"


class ContractType(str, Enum):
    CLT = "CLT"
    PJ = "PJ"


class SalaryPeriod(str, Enum):
    hour = "hour"
    month = "month"
    year = "year"


class Location(BaseModel):
    city: str = ""
    state: str = ""
    country: str = "BR"


class ProviderOverride(BaseModel):
    search_engines: list[str] | None = None
    crawlers: list[str] | None = None


class CompensationResearchRequest(BaseModel):
    profile: str = Field(min_length=3)
    skills: list[str] = Field(default_factory=list)
    seniority: str = ""
    allocation_model: AllocationModel = AllocationModel.remote
    location: Location = Field(default_factory=Location)
    target_contract: ContractType = ContractType.PJ
    providers: ProviderOverride | None = None
    force_refresh: bool = False
    source_job_id: str | None = None

    @field_validator("skills")
    @classmethod
    def normalize_skills(cls, skills: list[str]) -> list[str]:
        return [skill.strip() for skill in skills if skill and skill.strip()]


class NormalizedProfile(BaseModel):
    role_family: str = "technology"
    normalized_role: str
    seniority: str = ""
    specialization: str = ""
    skills: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    title: str = ""
    url: str
    snippet: str = ""
    provider: str
    rank: int = 0


class CrawledDocument(BaseModel):
    url: str
    source: str
    title: str = ""
    content: str = ""
    html: str | None = None
    retrieved_at: str
    crawl_method: Literal["http", "playwright", "search_snippet"] = "http"
    status: Literal["success", "partial", "blocked", "failed"] = "success"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Salary(BaseModel):
    min: float | None = None
    max: float | None = None
    average: float | None = None
    currency: str = "BRL"
    period: SalaryPeriod = SalaryPeriod.month


class CompensationObservation(BaseModel):
    id: str = ""
    role: str = ""
    normalized_role: str = ""
    seniority: str = ""
    skills: list[str] = Field(default_factory=list)
    location: Location = Field(default_factory=Location)
    allocation_model: AllocationModel | None = None
    employment_type: ContractType | None = None
    salary: Salary
    source: str
    source_url: str
    evidence: str
    evidence_type: Literal[
        "structured_data",
        "page_content",
        "search_snippet",
        "job_posting",
        "salary_report",
    ] = "page_content"
    source_date: str = ""
    retrieved_at: str
    crawl_method: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    observed_salary: dict[str, Any] = Field(default_factory=dict)
    normalized_salary: dict[str, Any] = Field(default_factory=dict)
    excluded_from_statistics: bool = False


class MarketStats(BaseModel):
    currency: str = "BRL"
    unit: Literal["hour", "month"] = "hour"
    contract_type: ContractType = ContractType.PJ
    minimum: float | None = None
    p25: float | None = None
    median: float | None = None
    mean: float | None = None
    p75: float | None = None
    maximum: float | None = None
    monthly_equivalent: float | None = None
    recommended_range: dict[str, float | None] = Field(default_factory=lambda: {"min": None, "max": None})


class SampleSummary(BaseModel):
    observations: int = 0
    sources: int = 0


class ProviderSummary(BaseModel):
    search_engines_used: list[str] = Field(default_factory=list)
    crawlers_used: list[str] = Field(default_factory=list)


class ConfidenceSummary(BaseModel):
    score: float = Field(ge=0, le=1)
    level: Literal["HIGH", "MEDIUM", "LOW"]


class SourceSummary(BaseModel):
    name: str
    url: str
    observations: int
    retrieved_at: str = ""


class CompensationResearchResponse(BaseModel):
    research_id: str
    profile: NormalizedProfile
    market: MarketStats
    sample: SampleSummary
    providers: ProviderSummary
    confidence: ConfidenceSummary
    sources: list[SourceSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    observations: list[CompensationObservation] = Field(default_factory=list)
    created_at: datetime
