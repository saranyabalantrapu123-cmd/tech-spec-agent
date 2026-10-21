"""Prompt templates for the four pipeline stages (extract -> draft -> critique -> revise)."""

from __future__ import annotations

import json
from typing import Any

from .conventions import APPROVED_ACTIONS, REQUIRED_GLOBAL_PROPERTIES, VAGUE_TERMS

SYSTEM = """You are a senior technical program manager and analytics-instrumentation lead at \
Nimbus Wireless, a mobile carrier (brands: Nimbus Wireless, Nimbus Prepaid). You turn feature \
requests into precise, testable technical specifications that engineering, QA and analytics can \
build from without a follow-up meeting.

Hard rules:
1. Never invent product facts. Every requirement with source="input" must cite the fact IDs (F-n) \
it comes from in `refs`. Anything you add that the input does not state is source="assumption" and \
must reference an Assumption (A-n) you list in `assumptions`.
2. When the input is ambiguous or silent on something that blocks build, add an OpenQuestion \
(OQ-n) instead of guessing, and reference it (e.g. "target TBD (OQ-2)").
3. Requirements are single, testable statements with IDs FR-n / NFR-n. Avoid vague words \
(""" + ", ".join(VAGUE_TERMS[:14]) + """, ...) unless tied to a measurable threshold or an open \
question. Every NFR has a number or an OQ reference.
4. User stories (US-n) each have Given/When/Then acceptance criteria.
5. Tracking events: snake_case <object>_<action>, action is a past-tense verb from: \
""" + ", ".join(sorted(APPROVED_ACTIONS)) + """. Every event has a precise trigger, platforms \
(app/web), typed properties (snake_case, enum properties list allowed_values). Declare these \
global properties once in analytics.global_properties: """ + ", ".join(REQUIRED_GLOBAL_PROPERTIES) \
    + """. Reuse events from the existing event dictionary instead of creating near-duplicates.
6. The test plan references only requirement/story IDs and event names that exist in the spec.
"""

RUBRIC = """Rubric (score each 1-5):
- completeness: every section filled with content specific to this feature
- testability: requirements and acceptance criteria are verifiable, no vague wording
- instrumentation: events follow convention, have typed properties, map to success metrics, reuse \
the dictionary
- traceability: requirements cite facts/assumptions; tests cover requirements and events
- ambiguity_handling: gaps become open questions/assumptions rather than invented facts
- clarity: an engineer could start building without a meeting"""


def _dump(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, indent=1, default=str)


def extract_messages(request: str, context_docs: dict[str, str],
                     dictionary_names: list[str]) -> list[dict[str, str]]:
    ctx = "\n\n".join(f"### Context file: {name}\n{text}" for name, text in context_docs.items())
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"""Step 1 of 4 - EXTRACT.
Read the feature request (and any context files) and extract:
- atomic facts (F-1, F-2, ...) each with a verbatim source_quote and a category,
- ambiguities (AMB-n): anything unclear, unmeasurable, contradictory or missing that engineering \
would need (eligibility, targets, owners, platforms, data sources, edge cases),
- personas, platforms (app/web) explicitly mentioned, a snake_case feature_slug,
- relevant_existing_events: names from the event dictionary below that relate to this feature.
Do not add facts that are not in the text.

## Feature request
{request}

{ctx}

## Existing event dictionary (names)
{", ".join(dictionary_names) or "(none provided)"}"""},
    ]


def draft_messages(request: str, extraction: Any, dictionary_csv: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"""Step 2 of 4 - DRAFT the full technical specification.
Use ONLY the extracted facts as product facts; label everything else as assumptions; turn every \
ambiguity into an open question.

## Extraction
{_dump(extraction)}

## Original request (for wording)
{request}

## Existing event dictionary (CSV)
{dictionary_csv or "(none provided)"}"""},
    ]


def critique_messages(draft: Any, extraction: Any, deterministic_findings: list[str]
                      ) -> list[dict[str, str]]:
    findings = "\n".join(f"- {f}" for f in deterministic_findings) or "- (none)"
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"""Step 3 of 4 - CRITIQUE the draft against the rubric. Be \
specific: name the section/ID, the problem and the concrete fix. Flag any statement presented as \
fact that is not supported by the extraction.

{RUBRIC}

## Automated scorer and event-linter findings (already verified, include the important ones)
{findings}

## Extraction (the only allowed product facts)
{_dump(extraction)}

## Draft spec
{_dump(draft)}"""},
    ]


def revise_messages(draft: Any, critique: Any, extraction: Any) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"""Step 4 of 4 - REVISE. Return the complete improved \
specification, addressing every major and minor critique issue. Do not drop content that was \
correct. Where a fix needs information the input does not contain, add or reference an open \
question instead of inventing it.

## Critique
{_dump(critique)}

## Extraction
{_dump(extraction)}

## Draft spec
{_dump(draft)}"""},
    ]
