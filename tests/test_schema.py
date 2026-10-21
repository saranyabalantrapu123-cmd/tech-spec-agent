import pytest
from pydantic import ValidationError

from spec_agent.schema import EventProperty, Requirement, SpecContent, TechSpec, TrackingEvent


def test_good_spec_validates_and_round_trips(good_spec):
    restored = TechSpec.model_validate_json(good_spec.model_dump_json())
    assert restored == good_spec
    assert restored.user_stories[0].acceptance_criteria[0].then


def test_unknown_keys_are_rejected():
    # extra="forbid" makes LLM drift a validation error, which triggers the retry loop
    with pytest.raises(ValidationError):
        Requirement(id="FR-1", description="x", made_up_field=True)


def test_invalid_literals_are_rejected():
    with pytest.raises(ValidationError):
        Requirement(id="FR-1", description="x", source="vibes")
    with pytest.raises(ValidationError):
        TrackingEvent(name="a_viewed", description="d", trigger="t", platforms=["tv"])
    with pytest.raises(ValidationError):
        EventProperty(name="x", type="decimal", description="d")


def test_spec_content_has_every_required_section():
    fields = set(SpecContent.model_fields)
    for section in ["overview", "problem_statement", "goals", "non_goals", "user_stories",
                    "functional_requirements", "non_functional_requirements", "analytics",
                    "data_model_changes", "api_changes", "dependencies", "edge_cases", "rollout",
                    "test_plan", "risks", "assumptions", "open_questions"]:
        assert section in fields


def test_json_schema_is_generated_for_llm_prompting():
    schema = SpecContent.model_json_schema()
    assert "UserStory" in schema["$defs"] and "TrackingEvent" in schema["$defs"]
