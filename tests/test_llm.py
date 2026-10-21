import json
from types import SimpleNamespace

import pytest

from spec_agent.llm import LiteLLMClient, extract_json, get_client, is_offline
from spec_agent.mock_llm import MockLLM
from spec_agent.schema import Critique


def _response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                           usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))


def test_offline_detection(monkeypatch):
    assert is_offline() and isinstance(get_client(), MockLLM)
    monkeypatch.setenv("LLM_MODEL", "anthropic/claude-sonnet-4-5")
    assert is_offline()  # no key -> still offline
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert not is_offline()
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    assert is_offline()  # openai model needs OPENAI_API_KEY
    monkeypatch.setenv("LLM_MODEL", "mock")
    assert is_offline()


def test_extract_json_handles_fences_and_prose():
    assert extract_json('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('prefix {"a": {"b": 2}} suffix') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_structured_retries_on_validation_error_with_error_feedback():
    replies = iter(['{"rubric_scores": {"clarity": 3}, "issues": [{"section": "FR-1"}]}',
                    json.dumps({"rubric_scores": {"clarity": 4}, "issues": [], "summary": "ok"})])
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs["messages"])
        return _response(next(replies))

    client = LiteLLMClient(model="anthropic/test", completion_fn=fake_completion)
    out = client.structured("critique", [{"role": "user", "content": "go"}], Critique, {})
    assert out.summary == "ok" and len(calls) == 2
    assert "failed validation" in calls[1][-1]["content"]  # error fed back to the model
    stage = client.usage.stages[0]
    assert stage.attempts == 2 and stage.prompt_tokens == 200 and stage.completion_tokens == 40


def test_structured_gives_up_after_max_retries():
    client = LiteLLMClient(model="anthropic/test", max_retries=1,
                           completion_fn=lambda **_: _response("not json"))
    with pytest.raises(RuntimeError, match="after 2 attempts"):
        client.structured("critique", [{"role": "user", "content": "go"}], Critique, {})
