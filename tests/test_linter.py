from spec_agent.linter import canonical_key, lint_events, strict_key
from spec_agent.schema import EventProperty, PropertyType, TrackingEvent


def _event(name, props=None, status="new", platforms=("app", "web")):
    return TrackingEvent(name=name, description="d", trigger="fires when something happens",
                         platforms=list(platforms), status=status,
                         properties=props or [EventProperty(name="entry_point",
                                                            type=PropertyType.STRING,
                                                            description="d")])


def _rules(spec, dictionary):
    return {(f.event, f.rule) for f in lint_events(spec, dictionary).findings}


def test_dictionary_loads(dictionary):
    by = {d.name: d for d in dictionary}
    assert by["planCompareSelected"].properties == {"plan_id": "string",
                                                    "monthly_price": "string"}
    assert by["chat_escalated"].status == "deprecated"
    assert by["bill_viewed"].platforms == ("app", "web")


def test_keys_normalise_case_tense_and_synonyms():
    assert strict_key("planCompareSelected") == strict_key("plan_compare_select")
    assert strict_key("plan_comparison_viewed") != strict_key("plan_comparison_failed")
    assert canonical_key("trade_in_estimate_viewed") == canonical_key("trade_in_quote_viewed")
    assert canonical_key("bill_tapped") == canonical_key("bill_clicked")


def test_existing_event_marked_new_is_a_duplicate(good_spec, dictionary):
    good_spec.analytics.events = [_event("bill_viewed")]
    assert ("bill_viewed", "duplicate-event") in _rules(good_spec, dictionary)


def test_existing_event_extended_must_be_marked_modified(good_spec, dictionary):
    good_spec.analytics.events = [_event("trade_in_quote_viewed", status="existing")]
    rules = _rules(good_spec, dictionary)
    assert ("trade_in_quote_viewed", "existing-event-changed") in rules  # adds app + entry_point


def test_naming_drift_is_detected(good_spec, dictionary):
    good_spec.analytics.events = [_event("plan_compare_selected")]
    findings = lint_events(good_spec, dictionary).findings
    drift = [f for f in findings if f.rule == "naming-drift"]
    assert drift and drift[0].dictionary_match == "planCompareSelected"


def test_synonym_drift_is_detected(good_spec, dictionary):
    good_spec.analytics.events = [_event("trade_in_estimate_viewed")]
    assert ("trade_in_estimate_viewed", "synonym-drift") in _rules(good_spec, dictionary)


def test_possible_duplicate_requires_same_action(good_spec, dictionary):
    good_spec.analytics.events = [_event("billing_viewed"), _event("billing_failed")]
    rules = _rules(good_spec, dictionary)
    assert ("billing_viewed", "possible-duplicate") in rules
    assert not any(e == "billing_failed" for e, _ in rules)


def test_property_type_conflict_is_an_error(good_spec, dictionary):
    good_spec.analytics.events = [_event("plan_tile_selected", props=[
        EventProperty(name="monthly_price", type=PropertyType.NUMBER, description="d")])]
    report = lint_events(good_spec, dictionary)
    assert [f.rule for f in report.errors] == ["property-type-conflict"]


def test_deprecated_event_and_duplicates_within_spec(good_spec, dictionary):
    good_spec.analytics.events = [_event("chat_escalated", status="existing"),
                                  _event("chat_escalated", status="existing")]
    rules = _rules(good_spec, dictionary)
    assert ("chat_escalated", "deprecated-event") in rules
    assert ("chat_escalated", "duplicate-in-spec") in rules


def test_unrelated_event_is_clean(good_spec, dictionary):
    good_spec.analytics.events = [_event("roaming_pass_purchased_completed")]
    assert lint_events(good_spec, dictionary).findings == []
