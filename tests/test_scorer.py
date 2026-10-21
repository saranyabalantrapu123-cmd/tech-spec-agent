from spec_agent.conventions import find_vague_terms
from spec_agent.schema import AcceptanceCriterion, EventProperty, PropertyType, Requirement
from spec_agent.scorer import score_spec


def _category(report, name):
    return next(c for c in report.categories if c.name == name)


def _messages(report, name):
    return " | ".join(f"{f.location}: {f.message}" for f in _category(report, name).findings)


def test_good_spec_scores_full_marks(good_spec):
    report = score_spec(good_spec)
    assert report.total == 100, [f.message for f in report.findings]


def test_scoring_is_deterministic(good_spec):
    assert score_spec(good_spec) == score_spec(good_spec)


def test_find_vague_terms():
    assert find_vague_terms("Must be fast, user-friendly, intuitive etc.") == [
        "fast", "user-friendly", "intuitive", "etc"]
    assert find_vague_terms("Responds within 800 ms at p95.") == []
    assert find_vague_terms("breakfast is steadfast") == []  # whole words only


def test_vague_requirement_is_flagged(good_spec):
    good_spec.functional_requirements.append(Requirement(
        id="FR-2", description="The form should be fast and user-friendly, etc.", refs=["F-2"]))
    report = score_spec(good_spec)
    msgs = _messages(report, "Requirement quality")
    assert "FR-2" in msgs and "'fast'" in msgs and "'user-friendly'" in msgs and "'etc'" in msgs
    assert _category(report, "Requirement quality").score < 20


def test_vague_requirement_deferred_to_open_question_is_info_only(good_spec):
    good_spec.functional_requirements[0].description += " It must be fast (target TBD: OQ-1)."
    report = score_spec(good_spec)
    fr = [f for f in report.findings if f.location == "FR-1"]
    assert fr and all(f.severity == "info" for f in fr)


def test_nfr_without_threshold_and_bad_ids_are_flagged(good_spec):
    good_spec.non_functional_requirements.append(Requirement(
        id="PERF-9", category="reliability", description="The service is highly available.",
        refs=["F-1"]))
    msgs = _messages(score_spec(good_spec), "Requirement quality")
    assert "must be unique and look like NFR-<n>" in msgs
    assert "no measurable threshold" in msgs


def test_compound_requirement_is_flagged(good_spec):
    good_spec.functional_requirements[0].description = (
        "The form must save the card and the page must show a confirmation.")
    assert "Combines several requirements" in _messages(score_spec(good_spec),
                                                        "Requirement quality")


def test_assumption_requirement_must_reference_an_assumption(good_spec):
    good_spec.non_functional_requirements[0].refs = []
    assert "does not reference an Assumption" in _messages(score_spec(good_spec),
                                                           "Requirement quality")


def test_story_without_acceptance_criteria_is_flagged(good_spec):
    good_spec.user_stories[0].acceptance_criteria = []
    report = score_spec(good_spec)
    assert "no acceptance criteria" in _messages(report, "User stories & acceptance criteria")
    assert _category(report, "User stories & acceptance criteria").score == 0


def test_incomplete_given_when_then_is_flagged(good_spec):
    good_spec.user_stories[0].acceptance_criteria.append(
        AcceptanceCriterion(given="", when="they submit", then="it works nicely"))
    msgs = _messages(score_spec(good_spec), "User stories & acceptance criteria")
    assert "not a full Given/When/Then" in msgs


def test_bad_event_names_are_flagged(good_spec):
    ev = good_spec.analytics.events[0]
    for bad, expected in [("AutopayEnrollmentSubmitted", "not snake_case"),
                          ("autopay-enrollment", "not snake_case"),
                          ("autopay_enrollment", "not an approved past-tense verb"),
                          ("autopay_enrollment_submit", "not an approved past-tense verb")]:
        ev.name = bad
        good_spec.test_plan[1].events_verified = [bad]
        good_spec.analytics.success_metrics[0].events = [bad]
        msgs = _messages(score_spec(good_spec), "Tracking plan")
        assert expected in msgs, (bad, msgs)


def test_event_without_properties_or_globals_is_flagged(good_spec):
    good_spec.analytics.events[0].properties = []
    good_spec.analytics.global_properties = []
    msgs = _messages(score_spec(good_spec), "Tracking plan")
    assert "no event-specific properties" in msgs
    assert "missing required properties: platform, brand, session_id" in msgs


def test_enum_without_values_and_bad_property_name_are_flagged(good_spec):
    good_spec.analytics.events[0].properties.append(
        EventProperty(name="cardType", type=PropertyType.ENUM, description="x"))
    msgs = _messages(score_spec(good_spec), "Tracking plan")
    assert "'cardType' is not snake_case" in msgs
    assert "enum property 'cardType' has no allowed_values" in msgs


def test_test_plan_referencing_unknown_event_is_flagged(good_spec):
    good_spec.test_plan[1].events_verified = ["autopay_ghost_viewed"]
    report = score_spec(good_spec)
    msgs = _messages(report, "Consistency & traceability")
    assert "'autopay_ghost_viewed' which is not in the tracking plan" in msgs
    assert "not verified by any test case" in msgs
    assert _category(report, "Consistency & traceability").score < 15


def test_metric_referencing_unknown_event_is_flagged(good_spec):
    good_spec.analytics.success_metrics[0].events = ["nope_viewed"]
    assert "Metric uses event 'nope_viewed'" in _messages(score_spec(good_spec),
                                                          "Consistency & traceability")


def test_missing_sections_reduce_completeness(good_spec):
    good_spec.risks = []
    good_spec.non_goals = []
    good_spec.rollout = None
    report = score_spec(good_spec)
    cat = _category(report, "Section completeness")
    assert cat.score == round(20 * 13 / 16, 1)
    assert {"Risks", "Non-goals", "Rollout plan"} <= {f.location for f in cat.findings}


def test_dangling_open_question_reference_and_no_questions(good_spec):
    good_spec.functional_requirements[0].description += " Limits per OQ-7."
    assert "Referenced open question does not exist" in _messages(score_spec(good_spec),
                                                                  "Ambiguity handling")
    good_spec.open_questions = []
    assert _category(score_spec(good_spec), "Ambiguity handling").score < 10
