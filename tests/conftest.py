"""Shared fixtures. Every test runs offline: LLM_MODEL=mock and no API keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_agent.linter import load_event_dictionary
from spec_agent.schema import (
    AcceptanceCriterion,
    AnalyticsPlan,
    Assumption,
    DataModelChange,
    Dependency,
    EdgeCase,
    EventProperty,
    OpenQuestion,
    PropertyType,
    Requirement,
    Risk,
    RolloutPhase,
    RolloutPlan,
    SpecMeta,
    SuccessMetric,
    TechSpec,
    TestCase,
    TrackingEvent,
    UserStory,
)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "inputs"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "mock")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def dictionary():
    return load_event_dictionary(FIXTURES / "event_dictionary.csv")


def _globals() -> list[EventProperty]:
    return [
        EventProperty(name="platform", type=PropertyType.ENUM, allowed_values=["app", "web"],
                      description="Surface"),
        EventProperty(name="brand", type=PropertyType.ENUM,
                      allowed_values=["nimbus_wireless", "nimbus_prepaid"], description="Brand"),
        EventProperty(name="session_id", type=PropertyType.STRING, description="Session"),
    ]


def build_good_spec() -> TechSpec:
    """A small, hand-written spec that satisfies every scorer rule."""
    event = TrackingEvent(
        name="autopay_enrollment_submitted", description="Customer submitted AutoPay enrollment",
        trigger="Server confirms the AutoPay enrollment request", platforms=["app", "web"],
        properties=[EventProperty(name="payment_method_type", type=PropertyType.ENUM,
                                  allowed_values=["card", "bank"], description="Method type")],
        related_requirements=["FR-1"])
    return TechSpec(
        meta=SpecMeta(mode="offline-demo", model="mock"),
        title="AutoPay enrollment from the bill page",
        overview="Let customers enrol in AutoPay directly from the bill page on app and web.",
        problem_statement="Customers must leave the bill page and navigate settings to enrol.",
        goals=["Increase AutoPay enrollment by 10% in 90 days"],
        non_goals=["Changing AutoPay discount amounts"],
        user_stories=[UserStory(
            id="US-1", as_a="Nimbus Wireless customer", i_want="to enrol in AutoPay from my bill",
            so_that="I never miss a payment", priority="must",
            acceptance_criteria=[AcceptanceCriterion(
                given="a signed-in account owner on the bill page",
                when="they submit the AutoPay form with a valid card",
                then="AutoPay shows as active on the bill page")])],
        functional_requirements=[Requirement(
            id="FR-1", description="The bill page offers an AutoPay enrollment form.",
            priority="must", refs=["F-1"])],
        non_functional_requirements=[Requirement(
            id="NFR-1", category="performance", priority="should", source="assumption",
            description="The enrollment request completes within 2 seconds at p95.",
            refs=["A-1"])],
        analytics=AnalyticsPlan(
            global_properties=_globals(), events=[event],
            success_metrics=[SuccessMetric(name="AutoPay enrollment rate", target="+10%",
                                           definition="Enrollments per bill-page session",
                                           events=["autopay_enrollment_submitted"])]),
        data_model_changes=[DataModelChange(entity="Event dictionary", change_type="add",
                                            fields=["autopay_enrollment_submitted"],
                                            description="Register event")],
        dependencies=[Dependency(name="Payments Service", type="service",
                                 description="Stores payment methods")],
        edge_cases=[EdgeCase(id="EC-1", scenario="Card is declined",
                             expected_behavior="Show the decline reason; AutoPay stays off")],
        rollout=RolloutPlan(feature_flag="autopay_bill_page_enabled", rollback_plan="Flag off",
                            phases=[RolloutPhase(name="Pilot", audience="5% of accounts",
                                                 exposure_percent=5, exit_criteria="No P1s")]),
        test_plan=[
            TestCase(id="TC-1", title="Enrol with a valid card", type="e2e",
                     steps=["Open bill page", "Submit form"], expected_result="AutoPay active",
                     covers=["FR-1", "US-1"]),
            TestCase(id="TC-2", title="Enrollment event payload", type="analytics",
                     steps=["Submit form"], expected_result="Event fires once",
                     covers=["FR-1"], events_verified=["autopay_enrollment_submitted"]),
        ],
        risks=[Risk(description="Payments Service latency", likelihood="low", impact="medium",
                    mitigation="Timeout and retry")],
        assumptions=[Assumption(id="A-1", statement="2 s p95 matches the payments SLO",
                                validate_with="Payments engineering")],
        open_questions=[OpenQuestion(id="OQ-1", question="Can sub-users enrol in AutoPay?",
                                     why_it_matters="Changes eligibility checks and UI states")],
    )


@pytest.fixture
def good_spec() -> TechSpec:
    return build_good_spec()
