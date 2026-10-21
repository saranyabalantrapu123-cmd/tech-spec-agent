import re

import pytest

from spec_agent.__main__ import main
from spec_agent.linter import load_event_dictionary
from spec_agent.mock_llm import (
    MockLLM,
    _ambiguity_question,
    _feature_slug,
    _i_want,
    _present_tense,
    parse_request,
)
from spec_agent.pipeline import enforce_provenance, run_pipeline
from spec_agent.schema import Requirement

from .conftest import EXAMPLES

EXAMPLE_FILES = sorted(EXAMPLES.glob("*.md"))
DICT = EXAMPLES / "event_dictionary.csv"


def test_examples_exist():
    assert len(EXAMPLE_FILES) == 3 and DICT.exists()


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.stem)
def test_mock_pipeline_end_to_end(path):
    text = path.read_text()
    result = run_pipeline(text, dictionary=load_event_dictionary(DICT), source_file=path.name)
    spec = result.spec
    assert isinstance(result.client, MockLLM) and result.offline
    assert spec.meta.mode == "offline-demo" and spec.meta.pipeline == "full"
    assert [s.stage for s in result.client.usage.stages] == ["extract", "draft", "critique",
                                                            "revise"]
    # Never invent product facts: every input-sourced requirement cites an extracted fact and
    # restates text that is actually in the request.
    fact_ids = {f.id for f in result.extraction.facts}
    facts = {f.id: f for f in result.extraction.facts}
    for req in spec.functional_requirements + spec.non_functional_requirements:
        if req.source == "input":
            cited = [r for r in req.refs if r in fact_ids]
            assert cited, req.id
            assert facts[cited[0]].source_quote in text
        else:
            assert any(r.startswith("A-") for r in req.refs), req.id
    assert result.guardrail_notes == []
    assert spec.open_questions and spec.user_stories and spec.analytics.events
    assert all(s.acceptance_criteria for s in spec.user_stories)
    assert result.score.total >= 95
    assert result.score.total >= result.draft_score.total
    assert result.critique is not None and result.critique.issues


def test_single_pass_baseline_skips_critique():
    text = (EXAMPLES / "trade_in_estimate.md").read_text()
    result = run_pipeline(text, single_pass=True)
    assert result.critique is None and result.spec.meta.pipeline == "single-pass"
    assert [s.stage for s in result.client.usage.stages] == ["extract", "draft"]


def test_revise_fixes_vague_requirements():
    text = (EXAMPLES / "trade_in_estimate.md").read_text()
    result = run_pipeline(text)
    draft_errors = [f for f in result.draft_score.findings
                    if f.severity == "error" and "Untestable" in f.message]
    final_errors = [f for f in result.score.findings
                    if f.severity == "error" and "Untestable" in f.message]
    assert draft_errors and not final_errors
    assert any("OQ-" in r.description for r in result.spec.non_functional_requirements)


def test_plain_text_request_without_headings_works():
    text = ("Customers should be able to pause their line for up to 30 days from the app. "
            "We want to reduce cancellations. Not sure if prepaid lines are eligible.")
    result = run_pipeline(text)
    assert result.spec.functional_requirements
    assert any("prepaid" in q.question.lower() for q in result.spec.open_questions)
    assert result.score.total > 50


def test_provenance_guardrail_relabels_untraceable_requirement():
    text = (EXAMPLES / "trade_in_estimate.md").read_text()
    result = run_pipeline(text, single_pass=True)
    spec = result.spec
    spec.functional_requirements.append(
        Requirement(id="FR-99", description="Offer a $50 bonus for trade-ins.", refs=[]))
    notes = enforce_provenance(spec, result.extraction, text)
    added = spec.functional_requirements[-1]
    assert added.source == "assumption" and added.refs[-1].startswith("A-")
    assert any("FR-99" in n for n in notes)
    assert spec.assumptions[-1].id == added.refs[-1]


def test_mock_text_heuristics():
    parsed = parse_request((EXAMPLES / "plan_comparison.md").read_text())
    assert parsed.title == "Unified plan comparison page across app and web"
    assert parsed.meta["platforms"] == "app and web"
    assert _feature_slug("Trade-in estimate in phone checkout") == "trade_in_estimate"
    assert _feature_slug("AI chat assistant entry point on the bill page") == "ai_chat_assistant"
    assert _ambiguity_question("Not sure yet if Nimbus Prepaid customers are eligible.") == (
        "Are Nimbus Prepaid customers eligible?")
    assert _i_want("Customers must be able to skip the step.") == "to skip the step"
    assert _present_tense("The estimate must be applied as a credit.") == (
        "the estimate is applied as a credit")


def test_cli_generate_score_and_lint(tmp_path, capsys):
    src = EXAMPLES / "ai_chat_bill_page.md"
    assert main(["generate", str(src), "--out-dir", str(tmp_path), "--format", "md,docx,json",
                 "--event-dictionary", str(DICT)]) == 0
    out = capsys.readouterr().out
    assert "offline demo mode" in out and "Quality score" in out
    for ext in ("md", "docx", "json"):
        assert (tmp_path / f"ai_chat_bill_page.{ext}").exists()
    spec_json = str(tmp_path / "ai_chat_bill_page.json")
    assert main(["score", spec_json, "--min-score", "90"]) == 0
    assert re.search(r"Quality score: [\d.]+ / 100", capsys.readouterr().out)
    assert main(["score", spec_json, "--min-score", "101"]) == 1
    assert main(["lint", spec_json, "--event-dictionary", str(DICT)]) == 0
    assert "possible-duplicate" in capsys.readouterr().out
