"""Pydantic models for the extraction step, the technical spec, the critique and the score report.

The spec schema is the contract between the LLM (or the offline MockLLM) and every downstream
consumer: the scorer, the event linter and the renderers. Anything the input did not state must be
labelled with ``source="assumption"`` (and backed by an entry in ``assumptions``) or raised as an
``OpenQuestion`` instead of being presented as a product fact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["app", "web"]
Source = Literal["input", "assumption"]
Priority = Literal["must", "should", "could"]
Level = Literal["low", "medium", "high"]


class _Model(BaseModel):
    """Base model: reject unknown keys so LLM drift is caught by validation (and retried)."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------------------------
# Step (a): extraction
# --------------------------------------------------------------------------------------------


class Fact(_Model):
    id: str = Field(description="Stable fact ID, e.g. F-1")
    statement: str = Field(description="One atomic fact stated in the input, paraphrased minimally")
    category: Literal[
        "requirement", "goal", "non_goal", "constraint", "metric", "context", "dependency"
    ]
    source_quote: str = Field(description="Verbatim excerpt from the input that supports the fact")


class Ambiguity(_Model):
    id: str = Field(description="e.g. AMB-1")
    topic: str
    question: str = Field(description="The question that must be answered before build")
    why_it_matters: str
    quote: str | None = Field(default=None, description="Input excerpt that is ambiguous, if any")


class Extraction(_Model):
    title: str
    feature_slug: str = Field(description="snake_case slug used as the analytics event prefix")
    summary: str
    personas: list[str] = Field(default_factory=list)
    platforms: list[Platform] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    relevant_existing_events: list[str] = Field(
        default_factory=list, description="Names from the event dictionary that look relevant"
    )


# --------------------------------------------------------------------------------------------
# Spec building blocks
# --------------------------------------------------------------------------------------------


class AcceptanceCriterion(_Model):
    given: str
    when: str
    then: str


class UserStory(_Model):
    id: str = Field(description="e.g. US-1")
    as_a: str
    i_want: str
    so_that: str
    priority: Priority = "should"
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)


class Requirement(_Model):
    id: str = Field(description="FR-<n> for functional, NFR-<n> for non-functional")
    description: str = Field(description="A single, testable statement")
    priority: Priority = "should"
    category: str = Field(default="functional", description="e.g. functional, performance, privacy")
    source: Source = "input"
    refs: list[str] = Field(
        default_factory=list,
        description="Fact IDs (F-n) it derives from, assumption IDs (A-n), or open questions (OQ-n)",
    )


class PropertyType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    ENUM = "enum"
    ARRAY = "array"


class EventProperty(_Model):
    name: str = Field(description="snake_case property name")
    type: PropertyType
    required: bool = True
    description: str
    allowed_values: list[str] | None = Field(default=None, description="Required when type=enum")
    example: str | None = None


class TrackingEvent(_Model):
    name: str = Field(description="snake_case <object>_<past_tense_action>, e.g. plan_selected")
    description: str
    trigger: str = Field(description="Exactly when the event fires (client/server, UI moment)")
    platforms: list[Platform]
    properties: list[EventProperty] = Field(default_factory=list)
    status: Literal["new", "existing", "modified"] = "new"
    related_requirements: list[str] = Field(default_factory=list)


class SuccessMetric(_Model):
    name: str
    definition: str = Field(description="How it is computed, in terms of tracking events")
    target: str = Field(description="Target value, or 'TBD (OQ-n)' if the input gave none")
    events: list[str] = Field(default_factory=list)


class AnalyticsPlan(_Model):
    naming_convention: str = (
        "snake_case <object>_<action>; action is a past-tense verb (viewed, selected, submitted…)"
    )
    global_properties: list[EventProperty] = Field(
        default_factory=list, description="Properties attached to every event"
    )
    events: list[TrackingEvent] = Field(default_factory=list)
    success_metrics: list[SuccessMetric] = Field(default_factory=list)


class DataModelChange(_Model):
    entity: str
    change_type: Literal["add", "modify", "remove"]
    fields: list[str] = Field(default_factory=list)
    description: str
    source: Source = "assumption"


class ApiChange(_Model):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    change_type: Literal["add", "modify", "remove"]
    description: str
    source: Source = "assumption"


class Dependency(_Model):
    name: str
    type: Literal["service", "team", "vendor", "data", "legal", "other"]
    description: str
    source: Source = "input"


class EdgeCase(_Model):
    id: str = Field(description="e.g. EC-1")
    scenario: str
    expected_behavior: str
    source: Source = "assumption"


class RolloutPhase(_Model):
    name: str
    audience: str
    exposure_percent: int = Field(ge=0, le=100)
    exit_criteria: str


class Experiment(_Model):
    hypothesis: str
    variants: list[str]
    randomization_unit: str
    primary_metric: str
    guardrail_metrics: list[str] = Field(default_factory=list)
    minimum_detectable_effect: str = "TBD"


class RolloutPlan(_Model):
    feature_flag: str
    phases: list[RolloutPhase] = Field(default_factory=list)
    experiment: Experiment | None = None
    rollback_plan: str
    source: Source = "assumption"


class TestCase(_Model):
    __test__ = False  # stop pytest from trying to collect this model as a test class

    id: str = Field(description="e.g. TC-1")
    title: str
    type: Literal["unit", "integration", "e2e", "analytics", "accessibility", "performance"]
    steps: list[str]
    expected_result: str
    covers: list[str] = Field(default_factory=list, description="FR/NFR/US IDs covered")
    events_verified: list[str] = Field(default_factory=list, description="Tracking event names")


class Risk(_Model):
    description: str
    likelihood: Level
    impact: Level
    mitigation: str


class Assumption(_Model):
    id: str = Field(description="e.g. A-1")
    statement: str
    validate_with: str = Field(description="Who/what can confirm or reject it")


class OpenQuestion(_Model):
    id: str = Field(description="e.g. OQ-1")
    question: str
    why_it_matters: str
    suggested_owner: str = "Product"
    blocking: bool = False


# --------------------------------------------------------------------------------------------
# The spec
# --------------------------------------------------------------------------------------------


class SpecContent(_Model):
    """Everything the model writes. ``TechSpec`` adds run metadata the pipeline fills in."""

    title: str
    overview: str
    problem_statement: str
    goals: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    user_stories: list[UserStory] = Field(default_factory=list)
    functional_requirements: list[Requirement] = Field(default_factory=list)
    non_functional_requirements: list[Requirement] = Field(default_factory=list)
    analytics: AnalyticsPlan = Field(default_factory=AnalyticsPlan)
    data_model_changes: list[DataModelChange] = Field(default_factory=list)
    api_changes: list[ApiChange] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    edge_cases: list[EdgeCase] = Field(default_factory=list)
    rollout: RolloutPlan | None = None
    test_plan: list[TestCase] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)


class SpecMeta(BaseModel):
    mode: Literal["offline-demo", "llm"]
    model: str
    pipeline: Literal["full", "single-pass"] = "full"
    source_file: str | None = None
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )
    generator: str = "tech-spec-agent"


class TechSpec(SpecContent):
    meta: SpecMeta


# --------------------------------------------------------------------------------------------
# Step (c): critique, and the deterministic score report
# --------------------------------------------------------------------------------------------


class CritiqueIssue(_Model):
    section: str
    severity: Literal["info", "minor", "major"]
    issue: str
    suggestion: str


class Critique(_Model):
    rubric_scores: dict[str, int] = Field(
        default_factory=dict, description="Rubric criterion -> 1..5"
    )
    issues: list[CritiqueIssue] = Field(default_factory=list)
    summary: str = ""


class Finding(BaseModel):
    severity: Literal["info", "warning", "error"]
    location: str
    message: str


class CategoryScore(BaseModel):
    name: str
    score: float
    max_score: float
    findings: list[Finding] = Field(default_factory=list)


class ScoreReport(BaseModel):
    total: float
    max_total: float = 100
    categories: list[CategoryScore]

    @property
    def findings(self) -> list[Finding]:
        return [f for c in self.categories for f in c.findings]
