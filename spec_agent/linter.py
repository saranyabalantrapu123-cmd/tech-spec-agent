"""Tracking-plan linter: compare a spec's events against an existing event dictionary.

Catches the instrumentation problems that usually surface weeks after launch, in a dashboard:
re-implemented events, naming drift (``planCompareSelect`` vs ``plan_comparison_selected``),
property type conflicts and use of deprecated events.
"""

from __future__ import annotations

import csv
import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from .conventions import ACTION_SYNONYMS, OBJECT_SYNONYMS, to_snake_case
from .schema import TechSpec, TrackingEvent

SIMILARITY_THRESHOLD = 0.82


@dataclass(frozen=True)
class DictionaryEvent:
    name: str
    description: str
    platforms: tuple[str, ...]
    properties: dict[str, str]  # property name -> type
    status: str = "active"
    owner: str = ""


@dataclass(frozen=True)
class LintFinding:
    severity: Literal["info", "warning", "error"]
    event: str
    rule: str
    message: str
    suggestion: str = ""
    dictionary_match: str | None = None


@dataclass
class LintReport:
    dictionary_size: int
    checked_events: int
    findings: list[LintFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == "warning"]


def load_event_dictionary(path: str | Path) -> list[DictionaryEvent]:
    """Load a CSV with columns: event_name, description, trigger, platforms, properties, owner, status.

    ``platforms`` is ``|``-separated (``app|web``); ``properties`` is ``;``-separated ``name:type``.
    """
    events: list[DictionaryEvent] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("event_name") or "").strip()
            if not name:
                continue
            props: dict[str, str] = {}
            for chunk in (row.get("properties") or "").split(";"):
                if ":" in chunk:
                    prop, ptype = chunk.split(":", 1)
                    props[prop.strip()] = ptype.strip().lower()
            platforms = tuple(
                p.strip().lower() for p in (row.get("platforms") or "").split("|") if p.strip()
            )
            events.append(
                DictionaryEvent(
                    name=name,
                    description=(row.get("description") or "").strip(),
                    platforms=platforms,
                    properties=props,
                    status=(row.get("status") or "active").strip().lower(),
                    owner=(row.get("owner") or "").strip(),
                )
            )
    return events


def _depluralize(tok: str) -> str:
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") else tok


def strict_key(name: str) -> str:
    """Normalise only case, separators, plurals and verb tense (``Select`` -> ``selected``)."""
    tokens = []
    for tok in to_snake_case(name).split("_"):
        past = ACTION_SYNONYMS.get(tok)
        tokens.append(past if past and past[:4] == tok[:4] else _depluralize(tok))
    return "_".join(t for t in tokens if t)


def canonical_key(name: str) -> str:
    """Normalise case, separators, plurals and common synonyms so drifted names collide."""
    tokens = []
    for tok in to_snake_case(name).split("_"):
        tokens.append(_depluralize(ACTION_SYNONYMS.get(tok, OBJECT_SYNONYMS.get(tok, tok))))
    return "_".join(t for t in tokens if t)


def relevant_events(text: str, dictionary: Iterable[DictionaryEvent], limit: int = 8) -> list[str]:
    """Dictionary events whose name tokens overlap the given text (used to brief the model)."""
    words = set(to_snake_case(text).split("_"))
    scored = []
    for ev in dictionary:
        toks = [t for t in to_snake_case(ev.name).split("_") if len(t) > 2]
        overlap = sum(1 for t in toks if t in words)
        if overlap:
            scored.append((overlap / len(toks), ev.name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in scored[:limit]]


def _check_existing(event: TrackingEvent, match: DictionaryEvent) -> list[LintFinding]:
    out: list[LintFinding] = []
    if match.status == "deprecated":
        out.append(LintFinding("error", event.name, "deprecated-event",
                               f"'{match.name}' is deprecated in the event dictionary.",
                               "Use the replacement event named in the dictionary.", match.name))
    if event.status == "new":
        out.append(LintFinding("warning", event.name, "duplicate-event",
                               f"'{event.name}' already exists in the event dictionary but is "
                               "marked as new.",
                               "Reuse the existing event and set status to 'existing' or "
                               "'modified'.", match.name))
    added_platforms = set(event.platforms) - set(match.platforms)
    added_props = {p.name for p in event.properties} - set(match.properties)
    if (added_platforms or added_props) and event.status == "existing":
        what = ", ".join(sorted(added_platforms | added_props))
        out.append(LintFinding("warning", event.name, "existing-event-changed",
                               f"Spec extends existing event with: {what}.",
                               "Mark the event as 'modified' so the dictionary owner reviews it.",
                               match.name))
    return out


def lint_events(spec: TechSpec, dictionary: list[DictionaryEvent]) -> LintReport:
    """Lint every tracking event in ``spec`` against ``dictionary``."""
    report = LintReport(dictionary_size=len(dictionary), checked_events=len(spec.analytics.events))
    by_name = {ev.name: ev for ev in dictionary}
    by_strict: dict[str, DictionaryEvent] = {}
    by_key: dict[str, DictionaryEvent] = {}
    for ev in dictionary:
        by_strict.setdefault(strict_key(ev.name), ev)
        by_key.setdefault(canonical_key(ev.name), ev)

    # Registry of property types across the dictionary, to catch type conflicts.
    prop_types: dict[str, tuple[str, str]] = {}
    for ev in dictionary:
        for prop, ptype in ev.properties.items():
            prop_types.setdefault(prop, (ptype, ev.name))

    seen: dict[str, int] = {}
    for event in spec.analytics.events:
        seen[event.name] = seen.get(event.name, 0) + 1
        if seen[event.name] == 2:
            report.findings.append(LintFinding("error", event.name, "duplicate-in-spec",
                                               "Event is defined more than once in this spec.",
                                               "Merge the definitions."))

        if event.name in by_name:
            report.findings.extend(_check_existing(event, by_name[event.name]))
        elif strict_key(event.name) in by_strict:
            match = by_strict[strict_key(event.name)]
            report.findings.append(LintFinding(
                "warning", event.name, "naming-drift",
                f"'{event.name}' is the existing event '{match.name}' with different casing, "
                "separators, plural or tense.",
                f"Reuse '{match.name}'" + (
                    " and plan a migration to the snake_case convention."
                    if match.name != to_snake_case(match.name) else "."),
                match.name))
        elif canonical_key(event.name) in by_key:
            match = by_key[canonical_key(event.name)]
            report.findings.append(LintFinding(
                "warning", event.name, "synonym-drift",
                f"'{event.name}' matches existing event '{match.name}' once synonyms are "
                "normalised (e.g. estimate/quote, tap/click).",
                f"Confirm whether '{match.name}' already measures this action; reuse it if so.",
                match.name))
        else:
            key = canonical_key(event.name)
            action = key.rsplit("_", 1)[-1]
            # Different actions are different events by definition: only compare same-action keys.
            candidates = [k for k in by_key if k.rsplit("_", 1)[-1] == action]
            close = difflib.get_close_matches(key, candidates, n=1, cutoff=SIMILARITY_THRESHOLD)
            if close:
                match = by_key[close[0]]
                report.findings.append(LintFinding(
                    "warning", event.name, "possible-duplicate",
                    f"'{event.name}' is very similar to existing event '{match.name}'.",
                    "Confirm with the dictionary owner whether this is the same user action.",
                    match.name))

        for prop in event.properties:
            if prop.name in prop_types:
                dict_type, owner_event = prop_types[prop.name]
                if dict_type != prop.type.value:
                    report.findings.append(LintFinding(
                        "error", event.name, "property-type-conflict",
                        f"Property '{prop.name}' is '{prop.type.value}' here but '{dict_type}' "
                        f"in the dictionary (on '{owner_event}').",
                        "Align the type with the dictionary, or version the property.",
                        owner_event))
    return report
