"""The spec-generation pipeline: extract -> draft -> critique -> revise.

Each stage is a structured (pydantic-validated) LLM call. Between draft and revise the
deterministic scorer and event linter run, so the critique is grounded in verified findings, and
a provenance guardrail runs on the final spec so nothing reaches readers as an unlabelled fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import prompts
from .linter import DictionaryEvent, LintReport, lint_events, relevant_events
from .llm import LLMClient, get_client
from .schema import Assumption, Critique, Extraction, ScoreReport, SpecContent, SpecMeta, TechSpec
from .scorer import score_spec


@dataclass
class PipelineResult:
    spec: TechSpec
    extraction: Extraction
    draft: TechSpec
    draft_score: ScoreReport
    critique: Critique | None
    score: ScoreReport
    lint: LintReport | None
    guardrail_notes: list[str]
    client: LLMClient

    @property
    def offline(self) -> bool:
        return self.client.offline


def _wrap(content: SpecContent, client: LLMClient, pipeline: str,
          source_file: str | None) -> TechSpec:
    meta = SpecMeta(mode="offline-demo" if client.offline else "llm", model=client.model,
                    pipeline=pipeline, source_file=source_file)  # type: ignore[arg-type]
    return TechSpec(meta=meta, **content.model_dump())


def enforce_provenance(spec: TechSpec, extraction: Extraction, request_text: str) -> list[str]:
    """Guardrail: anything presented as coming from the input must be traceable to it.

    * A requirement with ``source="input"`` must cite an extracted fact ID; otherwise it is
      relabelled as an assumption and a matching Assumption entry is added.
    * A dependency with ``source="input"`` must be named in the request text.
    Returns human-readable notes describing every relabel (empty when nothing was changed).
    """
    notes: list[str] = []
    fact_ids = {f.id for f in extraction.facts}
    next_a = max((int(a.id.split("-")[1]) for a in spec.assumptions
                  if re.fullmatch(r"A-\d+", a.id)), default=0)
    for req in spec.functional_requirements + spec.non_functional_requirements:
        if req.source == "input" and not any(r in fact_ids for r in req.refs):
            next_a += 1
            aid = f"A-{next_a}"
            spec.assumptions.append(Assumption(
                id=aid, statement=f"{req.id} is not traceable to the request: "
                                  f"{req.description}", validate_with="Requesting product owner"))
            req.source = "assumption"
            req.refs.append(aid)
            notes.append(f"{req.id} cited no input fact -> relabelled as assumption {aid}")
    lowered = request_text.lower()
    for dep in spec.dependencies:
        if dep.source == "input" and dep.name.lower() not in lowered:
            dep.source = "assumption"
            notes.append(f"Dependency '{dep.name}' is not named in the request -> assumption")
    return notes


def _dictionary_csv(dictionary: list[DictionaryEvent]) -> str:
    rows = ["event_name,platforms,properties,status"]
    rows += [f"{d.name},{'|'.join(d.platforms)},"
             f"{';'.join(f'{k}:{v}' for k, v in d.properties.items())},{d.status}"
             for d in dictionary]
    return "\n".join(rows) if dictionary else ""


def run_pipeline(request_text: str, *, context_docs: dict[str, str] | None = None,
                 dictionary: list[DictionaryEvent] | None = None, source_file: str | None = None,
                 single_pass: bool = False, client: LLMClient | None = None) -> PipelineResult:
    """Generate a spec. ``single_pass=True`` is the no-critique baseline (extract + draft only)."""
    client = client or get_client()
    context_docs = context_docs or {}
    dictionary = dictionary or []
    ctx = {"request": request_text, "context_docs": context_docs, "dictionary": dictionary}

    extraction = client.structured(
        "extract", prompts.extract_messages(request_text, context_docs,
                                            [d.name for d in dictionary]), Extraction, ctx)
    # Deterministic top-up: make sure obviously related dictionary events are surfaced.
    for name in relevant_events(request_text, dictionary):
        if name not in extraction.relevant_existing_events:
            extraction.relevant_existing_events.append(name)

    draft_content = client.structured(
        "draft", prompts.draft_messages(request_text, extraction, _dictionary_csv(dictionary)),
        SpecContent, {**ctx, "extraction": extraction})
    draft = _wrap(draft_content, client, "single-pass" if single_pass else "full", source_file)
    draft_lint = lint_events(draft, dictionary) if dictionary else None
    draft_score = score_spec(draft, draft_lint)

    critique: Critique | None = None
    if single_pass:
        final = draft.model_copy(deep=True)
    else:
        findings = [f"[{c.name}] {f.location}: {f.message}" for c in draft_score.categories
                    for f in c.findings if f.severity != "info"]
        findings += [f"[event-linter:{f.rule}] {f.event}: {f.message} {f.suggestion}"
                     for f in (draft_lint.findings if draft_lint else [])]
        critique = client.structured(
            "critique", prompts.critique_messages(draft_content, extraction, findings), Critique,
            {**ctx, "extraction": extraction, "draft": draft_content, "score": draft_score,
             "lint": draft_lint})
        revised = client.structured(
            "revise", prompts.revise_messages(draft_content, critique, extraction), SpecContent,
            {**ctx, "extraction": extraction, "draft": draft_content, "critique": critique,
             "lint": draft_lint})
        final = _wrap(revised, client, "full", source_file)

    notes = enforce_provenance(final, extraction, request_text + " "
                               + " ".join(context_docs.values()))
    final_lint = lint_events(final, dictionary) if dictionary else None
    return PipelineResult(
        spec=final, extraction=extraction, draft=draft, draft_score=draft_score,
        critique=critique, score=score_spec(final, final_lint), lint=final_lint,
        guardrail_notes=notes, client=client)


def read_context_files(paths: list[str | Path]) -> dict[str, str]:
    return {Path(p).name: Path(p).read_text(encoding="utf-8") for p in paths}
