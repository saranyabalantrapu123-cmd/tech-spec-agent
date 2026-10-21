"""Shared LLM access layer (LiteLLM), identical in shape across the portfolio repos.

* Model comes from ``LLM_MODEL`` (default ``anthropic/claude-sonnet-4-5``); the key from
  ``ANTHROPIC_API_KEY`` (or ``OPENAI_API_KEY`` for ``openai/...`` models).
* If ``LLM_MODEL=mock`` or no key is configured, a deterministic ``MockLLM`` is used instead so the
  demo, the app and the tests run with no key and no network.
* ``structured()`` asks for JSON matching a pydantic model, validates it, and on a parse or
  validation error re-prompts with the exact error (up to ``max_retries`` times).
* Token usage and estimated cost are tracked per stage.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"
OFFLINE_BANNER = "Running in offline demo mode (no LLM key) — outputs are rule-based"

T = TypeVar("T", bound=BaseModel)


def get_model() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _has_key(model: str) -> bool:
    if model.startswith("openai/") or model.startswith("gpt-"):
        return bool(os.getenv("OPENAI_API_KEY"))
    if model.startswith("anthropic/") or model.startswith("claude"):
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))


def is_offline() -> bool:
    """True when the mock should be used (``LLM_MODEL=mock`` or no key for the chosen model)."""
    model = get_model()
    return model.lower() == "mock" or not _has_key(model)


@dataclass
class StageUsage:
    stage: str
    attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0


@dataclass
class UsageTracker:
    stages: list[StageUsage] = field(default_factory=list)

    @property
    def prompt_tokens(self) -> int:
        return sum(s.prompt_tokens for s in self.stages)

    @property
    def completion_tokens(self) -> int:
        return sum(s.completion_tokens for s in self.stages)

    @property
    def cost_usd(self) -> float:
        return round(sum(s.cost_usd for s in self.stages), 6)

    def summary(self) -> str:
        return (f"{len(self.stages)} LLM calls, {self.prompt_tokens} prompt + "
                f"{self.completion_tokens} completion tokens, est. ${self.cost_usd:.4f}")


class LLMClient(Protocol):
    """Interface used by the pipeline. ``context`` carries the raw structured inputs of the stage;
    real models read the rendered ``messages``, the offline MockLLM reads ``context``."""

    model: str
    offline: bool
    usage: UsageTracker

    def structured(self, stage: str, messages: list[dict[str, str]], response_model: type[T],
                   context: dict[str, Any]) -> T: ...


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences and leading/trailing prose."""
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model output")
    return json.loads(text[start:end + 1])


class LiteLLMClient:
    """Real model client. ``completion_fn`` is injectable so retry logic is testable offline."""

    offline = False

    def __init__(self, model: str | None = None, max_retries: int = 2, temperature: float = 0.2,
                 completion_fn: Callable[..., Any] | None = None) -> None:
        self.model = model or get_model()
        self.max_retries = max_retries
        self.temperature = temperature
        self.usage = UsageTracker()
        if completion_fn is None:
            import litellm  # imported lazily: keeps offline start-up fast

            completion_fn = litellm.completion
        self._completion = completion_fn

    def _record(self, usage: StageUsage, response: Any) -> None:
        u = getattr(response, "usage", None)
        if u is not None:
            usage.prompt_tokens += int(getattr(u, "prompt_tokens", 0) or 0)
            usage.completion_tokens += int(getattr(u, "completion_tokens", 0) or 0)
        try:
            import litellm

            usage.cost_usd += float(litellm.completion_cost(completion_response=response) or 0.0)
        except Exception:  # cost map may not know the model; tokens are still recorded
            pass

    def structured(self, stage: str, messages: list[dict[str, str]], response_model: type[T],
                   context: dict[str, Any]) -> T:
        schema = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
        convo = [
            *messages[:-1],
            {"role": messages[-1]["role"],
             "content": f"{messages[-1]['content']}\n\nReturn ONLY one JSON object (no prose, no "
                        f"code fences) that validates against this JSON schema:\n{schema}"},
        ]
        usage = StageUsage(stage=stage)
        self.usage.stages.append(usage)
        started = time.perf_counter()
        last_error = ""
        try:
            for _ in range(self.max_retries + 1):
                usage.attempts += 1
                response = self._completion(model=self.model, messages=convo,
                                            temperature=self.temperature, max_tokens=16000)
                self._record(usage, response)
                content = response.choices[0].message.content or ""
                try:
                    return response_model.model_validate(extract_json(content))
                except (ValueError, ValidationError) as exc:
                    last_error = str(exc)[:4000]
                    convo += [
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": "Your JSON failed validation:\n"
                                                    f"{last_error}\nReturn the corrected, complete "
                                                    "JSON object only."},
                    ]
        finally:
            usage.seconds = round(time.perf_counter() - started, 2)
        raise RuntimeError(f"[{stage}] output failed validation after {usage.attempts} attempts: "
                           f"{last_error}")


def get_client() -> LLMClient:
    """Return the real LiteLLM client, or the deterministic MockLLM in offline mode."""
    if is_offline():
        from .mock_llm import MockLLM

        return MockLLM()
    return LiteLLMClient()
