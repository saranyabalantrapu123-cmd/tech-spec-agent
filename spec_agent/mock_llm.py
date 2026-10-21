"""Deterministic, rule-based stand-in for the LLM (offline demo mode).

It implements the same four stages as the real model using keyword and sentence heuristics, so
the whole pipeline (and the scorer, linter, renderers, app and tests) runs with no key and no
network. It is intentionally conservative: it only restates sentences from the input as product
facts, labels every addition as an assumption, and turns gaps into open questions. Output is
always marked as offline demo output; it is not a substitute for a real model's drafting quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from .conventions import (
    BRAND_VALUES,
    OPEN_QUESTION_REF_RE,
    PLATFORM_VALUES,
    REQUIRED_GLOBAL_PROPERTIES,
    find_vague_terms,
    to_snake_case,
)
from .linter import DictionaryEvent, LintReport, relevant_events
from .llm import StageUsage, UsageTracker
from .schema import (
    AcceptanceCriterion,
    Ambiguity,
    AnalyticsPlan,
    ApiChange,
    Assumption,
    Critique,
    CritiqueIssue,
    DataModelChange,
    Dependency,
    EdgeCase,
    EventProperty,
    Experiment,
    Extraction,
    Fact,
    OpenQuestion,
    PropertyType,
    Requirement,
    Risk,
    RolloutPhase,
    RolloutPlan,
    ScoreReport,
    SpecContent,
    SuccessMetric,
    TestCase,
    TrackingEvent,
    UserStory,
)

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------------------------
# Text parsing
# ---------------------------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'“])")
_UNCERTAIN = re.compile(r"\b(not sure|unclear|not decided|undecided|tbd|may want|might|maybe|"
                        r"unknown|to be confirmed)\b|\?\s*$", re.IGNORECASE)
_GOAL = re.compile(r"\b(increase|reduce|improve|grow|lower|decrease|raise|cut|get)\b", re.I)
_METRIC = re.compile(r"\b(track|measure|instrument|monitor)\b", re.IGNORECASE)
_DEPENDENCY = re.compile(
    r"\b((?:[A-Z][\w&-]*\s){0,3}(?:Service|API|Platform|Catalog|Team))\b|\b(Legal|Compliance|"
    r"Privacy|Security)\b(?= (?:needs|must|has|to|review))")
_ELIGIBILITY = re.compile(r"\b(eligible|eligibility|see the|access|logged-out|logged out|"
                          r"sub-users?|non-owners?)\b", re.I)
_GENERIC_SLUG_WORDS = {"entry", "point", "page", "screen", "flow", "feature", "new", "unified",
                       "improved", "the", "a", "an", "add", "adding", "support", "for"}
_PREPOSITIONS = (" in ", " on ", " across ", " for ", " to ", " within ", " at ", " from ")
_SECTION_KINDS = [
    ("non_goal", ("out of scope", "non-goal", "non goal", "not in scope", "exclusion")),
    ("goal", ("success", "goal", "metric", "kpi", "outcome")),
    ("note", ("note", "open question", "question", "risk", "consideration", "assumption")),
    ("requirement", ("want", "requirement", "ask", "scope", "must", "proposal", "solution")),
    ("context", ("background", "context", "problem", "why", "today", "current")),
]


@dataclass
class ParsedRequest:
    title: str
    meta: dict[str, str]
    sections: list[tuple[str, list[str]]] = field(default_factory=list)  # (kind, items)

    @property
    def full_text(self) -> str:
        return " ".join(" ".join(items) for _, items in self.sections)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]


def _section_kind(heading: str) -> str:
    h = heading.lower()
    for kind, keys in _SECTION_KINDS:
        if any(k in h for k in keys):
            return kind
    return "auto"


def parse_request(text: str) -> ParsedRequest:
    """Split a markdown/plain feature request into title, ``**Key:** value`` meta and sections."""
    title = ""
    meta: dict[str, str] = {}
    sections: list[tuple[str, list[str]]] = []
    kind, items, para = "auto", [], []

    def flush_para() -> None:
        if para:
            items.extend(_sentences(" ".join(para)))
            para.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# ") and not title:
            title = re.sub(r"^(feature request|request|feature|prd)\s*[:\-–]\s*", "", line[2:],
                           flags=re.I).strip()
        elif line.startswith("#"):
            flush_para()
            if items:
                sections.append((kind, items))
            kind, items = _section_kind(line.lstrip("#")), []
        elif m := re.match(r"^\*\*(.+?):\*\*\s*(.+)$", line):
            meta[m.group(1).strip().lower()] = m.group(2).strip()
        elif re.match(r"^([-*•]|\d+[.)])\s+", line):
            flush_para()
            items.append(re.sub(r"^([-*•]|\d+[.)])\s+", "", line))
        elif not line:
            flush_para()
        else:
            para.append(line)
    flush_para()
    if items:
        sections.append((kind, items))
    if not title:
        first = sections[0][1][0] if sections else "Untitled feature"
        title = " ".join(first.rstrip(".").split()[:8])
    return ParsedRequest(title=title, meta=meta, sections=sections)


def _classify(sentence: str, section_kind: str) -> str:
    """Map a sentence to a fact category (or 'ambiguity')."""
    s = sentence.lower()
    if section_kind == "non_goal" or "out of scope" in s:
        return "non_goal"
    if _UNCERTAIN.search(sentence):
        return "ambiguity"
    if section_kind == "note":
        return "dependency" if _DEPENDENCY.search(sentence) else "context"
    if section_kind == "goal":
        if _METRIC.search(sentence):
            return "metric"
        return "goal" if _GOAL.search(sentence) else "constraint"
    if section_kind == "requirement":
        return "requirement"
    if section_kind == "context":
        return "context"
    if re.search(r"\b(must|should|need to|needs to|able to|shall|allow|show|display)\b", s):
        return "requirement"
    if _METRIC.search(sentence):
        return "metric"
    if _GOAL.search(sentence):
        return "goal"
    return "context"


def _split_goals(sentence: str) -> list[str]:
    body = re.sub(r"^(we want to|we'd like to|the goal is to|goal:)\s*", "", sentence.rstrip("."),
                  flags=re.I)
    parts = re.split(r",? and (?=(?:increase|reduce|improve|grow|lower|decrease|get|raise)\b)",
                     body, flags=re.I)
    return [p.strip()[0].upper() + p.strip()[1:] for p in parts if p.strip()]


def _feature_slug(title: str) -> str:
    head = f" {title} "
    for prep in _PREPOSITIONS:
        idx = head.lower().find(prep)
        if 0 < idx:
            head = head[:idx]
    words = [w for w in to_snake_case(head).split("_") if w and w not in _GENERIC_SLUG_WORDS]
    return "_".join(words[:3]) or "feature"


def _short_label(title: str) -> str:
    """'Trade-in estimate in phone checkout' -> 'trade-in estimate' (keeps acronyms like AI)."""
    head = f" {title} "
    for prep in _PREPOSITIONS:
        idx = head.lower().find(prep)
        if 0 < idx:
            head = head[:idx]
    words = [w if w.isupper() else w.lower() for w in head.split()
             if w.lower() not in _GENERIC_SLUG_WORDS]
    return " ".join(words) or title.lower()


def _ambiguity_question(sentence: str) -> str:
    s = sentence.strip().rstrip(".")
    if s.endswith("?"):
        return s
    m = re.search(r"(?:not sure|unclear|not decided|undecided)(?: yet)?\s+(?:if|whether)\s+(.+)",
                  s, re.I)
    if m:
        clause = m.group(1)
        aux = re.search(r"\b(are|is|should|can|will|must|do|does)\b", clause)
        if aux:
            before, after = clause[:aux.start()].strip(), clause[aux.end():].strip()
            return f"{aux.group(1).capitalize()} {before} {after}?"
        return f"Clarify whether {clause}?"
    m = re.search(r"\b(?:may|might) want to\s+(.+)", s, re.I)
    if m:
        return f"Should we {m.group(1)}?"
    return f"Clarify: {s}?"


def _owner_for(text: str) -> str:
    t = text.lower()
    if "legal" in t or "privacy" in t:
        return "Legal"
    if any(k in t for k in ("event", "metric", "target", "track", "care-contact", "experiment",
                            "a/b")):
        return "Analytics"
    if any(k in t for k in ("latency", "load", "respond", "fast", "quick", "api", "service")):
        return "Engineering"
    if any(k in t for k in ("intuitive", "easy", "modern", "accessib", "layout")):
        return "UX Design"
    return "Product"


# ---------------------------------------------------------------------------------------------
# Stage (a): extraction
# ---------------------------------------------------------------------------------------------


def mock_extract(request: str, context_docs: dict[str, str],
                 dictionary: list[DictionaryEvent]) -> Extraction:
    parsed = parse_request(request)
    facts: list[Fact] = []
    ambiguities: list[Ambiguity] = []

    def add_fact(statement: str, category: str, quote: str) -> None:
        facts.append(Fact(id=f"F-{len(facts) + 1}", statement=statement, category=category,
                          source_quote=quote))

    def add_amb(topic: str, question: str, why: str, quote: str | None = None) -> None:
        if all(a.question != question for a in ambiguities):
            ambiguities.append(Ambiguity(id=f"AMB-{len(ambiguities) + 1}", topic=topic,
                                         question=question, why_it_matters=why, quote=quote))

    sources = list(parsed.sections)
    for name, text in context_docs.items():
        sources.append(("auto", [s for s in _sentences(" ".join(text.split()))]))
    for kind, items in sources:
        for sentence in items:
            category = _classify(sentence, kind)
            if category == "ambiguity":
                add_amb("Unresolved decision", _ambiguity_question(sentence),
                        "The request explicitly leaves this open; it changes scope or "
                        "eligibility logic.", sentence)
            elif category == "goal":
                for goal in _split_goals(sentence):
                    add_fact(goal, "goal", sentence)
            else:
                add_fact(sentence.rstrip(), category, sentence)
            if category == "dependency" and re.search(r"\breview\b", sentence, re.I):
                dep = _DEPENDENCY.search(sentence)
                rest = re.split(r"\breview\b\s*", sentence.rstrip("."), maxsplit=1, flags=re.I)[-1]
                add_amb("Approval", f"What will {(dep.group(0) if dep else 'the reviewer')} "
                                    f"approve regarding {rest}?",
                        "Build cannot be finalised until the review outcome is known.", sentence)

    for fact in facts:
        if fact.category == "requirement":
            vague = find_vague_terms(fact.statement)
            if vague:
                add_amb("Measurable target",
                        f"What measurable target defines {', '.join(repr(v) for v in vague)} in: "
                        f"\"{fact.statement.rstrip('.')}\"?",
                        "Without a threshold the requirement cannot be tested or accepted.",
                        fact.source_quote)
        if fact.category == "goal" and not re.search(r"\d", fact.statement):
            add_amb("Success target", f"What is the target and timeframe for: "
                                      f"\"{fact.statement}\"?",
                    "Success metrics need a target to size the rollout and judge the launch.",
                    fact.source_quote)
        if fact.category == "goal" and re.search(r"\b(calls?|care|contacts?)\b", fact.statement,
                                                 re.I):
            add_amb("Data source", "Which care-contact data source and reason codes identify the "
                                   f"calls in: \"{fact.statement}\"?",
                    "The metric cannot be computed from app/web events alone.",
                    fact.source_quote)

    text = request + " " + " ".join(context_docs.values())
    if re.search(r"\b(a/b|experiment)\b", text, re.I):
        add_amb("Experiment design", "What are the primary metric, minimum detectable effect and "
                                     "planned duration of the experiment?",
                "Needed to size the test and decide when to stop it.")
    platforms_raw = parsed.meta.get("platforms", "") + " " + parsed.title
    platforms = [p for p in PLATFORM_VALUES if re.search(rf"\b{p}\b", platforms_raw, re.I)]
    if not platforms:
        platforms = [p for p in PLATFORM_VALUES if re.search(rf"\b{p}\b", text, re.I)]
    if not platforms:
        add_amb("Platforms", "Which platforms (app, web) are in scope?",
                "Determines engineering scope and where events must be implemented.")

    brand = parsed.meta.get("brand", "Nimbus Wireless")
    persona = ("Nimbus Wireless or Nimbus Prepaid customer"
               if "prepaid" in brand.lower() and "wireless" in brand.lower()
               else f"{brand} customer")
    context_sentences = [f.statement for f in facts if f.category == "context"]
    summary = " ".join(context_sentences[:2]) or parsed.title
    return Extraction(
        title=parsed.title,
        feature_slug=_feature_slug(parsed.title),
        summary=summary,
        personas=[persona],
        platforms=platforms,  # type: ignore[arg-type]
        facts=facts,
        ambiguities=ambiguities,
        relevant_existing_events=relevant_events(text, dictionary),
    )


# ---------------------------------------------------------------------------------------------
# Stage (b): draft
# ---------------------------------------------------------------------------------------------

_PROP_KEYWORDS: list[tuple[str, EventProperty]] = [
    (r"device model", EventProperty(name="device_model", type=PropertyType.STRING,
                                    description="Device model the customer entered")),
    (r"condition", EventProperty(name="device_condition", type=PropertyType.STRING,
                                 description="Condition grade selected (values per OQ / service)")),
    (r"estimate", EventProperty(name="estimate_amount", type=PropertyType.NUMBER,
                                description="Estimated value shown, in USD")),
    (r"bill period", EventProperty(name="bill_period", type=PropertyType.STRING,
                                   description="Bill period in context, YYYY-MM", example="2026-09")),
    (r"\bplans?\b", EventProperty(name="plan_id", type=PropertyType.STRING,
                                  description="Catalog ID of the plan")),
    (r"monthly price", EventProperty(name="monthly_price", type=PropertyType.NUMBER,
                                     description="Monthly price shown, in USD")),
    (r"number of lines", EventProperty(name="line_count", type=PropertyType.INTEGER,
                                       description="Number of lines selected")),
]

# keyword in the ask -> (event suffix, description, trigger template, extra properties)
_KEYWORD_EVENTS: list[tuple[str, str, str, str, list[EventProperty]]] = [
    (r"\bskip", "skipped", "Customer skipped the {label} step",
     "Customer taps the skip control on the {label} step", [
         EventProperty(name="step_name", type=PropertyType.STRING,
                       description="Name of the skipped step")]),
    (r"\b(message|chat)\b", "message_sent", "Customer sent a message in the {label}",
     "Message is submitted from the {label} input (fires on client send)", [
         EventProperty(name="message_count", type=PropertyType.INTEGER,
                       description="Count of customer messages in the session so far"),
         EventProperty(name="message_length", type=PropertyType.INTEGER,
                       description="Characters in the message (content is never sent)")]),
    (r"escalat", "escalated", "Conversation escalated to a live agent",
     "Customer confirms the escalate-to-agent action and the handoff request is accepted", [
         EventProperty(name="message_count", type=PropertyType.INTEGER,
                       description="Customer messages before escalation"),
         EventProperty(name="escalation_reason", type=PropertyType.STRING, required=False,
                       description="Reason selected by the customer, if any")]),
    (r"\b(rate|rating|thumbs|feedback)\b", "feedback_submitted",
     "Customer rated an answer", "Customer taps thumbs up or thumbs down on an answer", [
         EventProperty(name="rating", type=PropertyType.ENUM, allowed_values=["thumbs_up",
                                                                              "thumbs_down"],
                       description="Rating given"),
         EventProperty(name="answer_id", type=PropertyType.STRING,
                       description="ID of the rated answer")]),
    (r"\bselect", "selected", "Customer selected an item to compare or buy",
     "Customer taps the select control on an item card", [
         EventProperty(name="position", type=PropertyType.INTEGER,
                       description="1-based position of the item on the page")]),
    (r"\bfilter", "filter_applied", "Customer applied a filter",
     "Filter value changes and results re-render", [
         EventProperty(name="filter_name", type=PropertyType.STRING, description="Filter used"),
         EventProperty(name="filter_value", type=PropertyType.STRING,
                       description="Value chosen")]),
]


def _ptype(raw: str) -> PropertyType:
    try:
        return PropertyType(raw)
    except ValueError:
        return PropertyType.STRING


def _global_properties() -> list[EventProperty]:
    return [
        EventProperty(name="platform", type=PropertyType.ENUM, allowed_values=PLATFORM_VALUES,
                      description=REQUIRED_GLOBAL_PROPERTIES["platform"]),
        EventProperty(name="brand", type=PropertyType.ENUM, allowed_values=BRAND_VALUES,
                      description=REQUIRED_GLOBAL_PROPERTIES["brand"]),
        EventProperty(name="session_id", type=PropertyType.STRING,
                      description=REQUIRED_GLOBAL_PROPERTIES["session_id"]),
    ]


_LEADING_CLAUSE = re.compile(r"^(when|if|after|before|once)\s+([^,]+),\s*(.+)$", re.I)
_CUSTOMER_ABLE = re.compile(
    r"^(?:customers|users)\s+(?:must|should|can|will)\s+(?:be able to\s+)?(.*)$", re.I)


def _move_leading_clause(statement: str) -> str:
    """'When opened from X, the assistant must Y' -> 'the assistant must Y when opened from X'."""
    s = statement.strip().rstrip(".")
    m = _LEADING_CLAUSE.match(s)
    return f"{m.group(3)} {m.group(1).lower()} {m.group(2)}" if m else s


def _verb3(v: str) -> str:
    if v.endswith("y") and v[-2:-1] not in "aeiou":
        return v[:-1] + "ies"
    return v + ("es" if re.search(r"(s|sh|ch|x|o)$", v) else "s")


def _present_tense(statement: str) -> str:
    """'The estimate must be applied …' -> 'the estimate is applied …' (rule-based)."""
    s = _move_leading_clause(statement)
    s = re.sub(r"^(customers|users)\s+(must|should|can|will)\s+be able to\b", "the customer can",
               s, flags=re.I)
    s = re.sub(r"\b(must|should|will)\s+never\s+(\w+)", lambda m: f"never {_verb3(m.group(2))}",
               s, flags=re.I)
    s = re.sub(r"\b(must|should|will)\s+not\s+(\w+)", lambda m: f"does not {m.group(2)}", s,
               flags=re.I)
    s = re.sub(r"\b(must|should|will)\s+be\b", "is", s, flags=re.I)
    s = re.sub(r"\b(must|should|will)\s+(\w+)", lambda m: _verb3(m.group(2)), s, flags=re.I)
    s = re.sub(r"^(show|display)\b", "the page shows", s, flags=re.I)
    s = re.sub(r"^(add|provide)\b", "there is", s, flags=re.I)
    s = re.sub(r"^(a|an)\s+(single\s+)?", lambda m: f"there is {m.group(0).lower()}", s,
               flags=re.I)
    return s[0].lower() + s[1:] if s else s


def _first_person(text: str) -> str:
    text = re.sub(r"\btheir\b", "my", text)
    text = re.sub(r"\bthe customer does\b", "I do", text)
    text = re.sub(r"\bthe customer\b", "me", text)
    return re.sub(r"\bthey\b", "I", text)


def _i_want(statement: str) -> str:
    """Rewrite a requirement sentence as the 'I want …' part of a user story."""
    s = _move_leading_clause(statement)
    if m := _CUSTOMER_ABLE.match(s):
        return _first_person(f"to {m.group(1)}")
    if m := re.match(r"^(?:show|display)\s+(.*)$", s, re.I):
        return f"to see {m.group(1)}"
    if m := re.match(r"^(?:add|provide)\s+(.*)$", s, re.I):
        return m.group(1)
    if m := re.match(r"^(.*?)\s+(?:must|should|will)\s+(never\s+)?(.*)$", s, re.I):
        subject = m.group(1)[0].lower() + m.group(1)[1:]
        return _first_person(f"{subject} to {m.group(2) or ''}{m.group(3)}")
    return _first_person(s[0].lower() + s[1:])


def _customer_action(statement: str) -> str | None:
    """Third-person action for a 'When' clause, if the sentence describes a customer action."""
    m = _CUSTOMER_ABLE.match(_move_leading_clause(statement))
    return m.group(1) if m else None


def _is_nfr(statement: str) -> str | None:
    s = statement.lower()
    if find_vague_terms(statement) and re.search(r"\b(load|respond|fast|quick|intuitive|easy|"
                                                 r"modern|accessib|look)", s):
        return "performance & usability"
    if re.search(r"\b(never display|must never|card numbers?|bank account|pii|encrypt)", s):
        return "privacy & security"
    return None


@dataclass
class _Ids:
    counters: dict[str, int] = field(default_factory=dict)

    def next(self, prefix: str) -> str:
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}-{self.counters[prefix]}"


def _build_events(ext: Extraction, text: str, dictionary: list[DictionaryEvent],
                  label: str) -> list[TrackingEvent]:
    slug, platforms = ext.feature_slug, list(ext.platforms) or ["app", "web"]
    lower = text.lower()
    entity_props = [p for kw, p in _PROP_KEYWORDS if re.search(kw, lower)]
    entry = EventProperty(name="entry_point", type=PropertyType.STRING,
                          description="Screen or link the customer came from")
    events: list[TrackingEvent] = []
    viewed = f"{slug}_entry_viewed" if "entry point" in lower else f"{slug}_viewed"
    shown = f"{label} entry point" if viewed.endswith("_entry_viewed") else label
    events.append(TrackingEvent(
        name=viewed, description=f"The {shown} is displayed to the customer",
        trigger=f"Fires once per page load when the {shown} is at least 50% in the viewport",
        platforms=platforms, properties=[entry, EventProperty(
            name="screen_name", type=PropertyType.STRING, description="App screen or web page")]))
    start_verb = ("opened" if re.search(r"\bopens?\b", lower)
                  else "started" if re.search(r"\b(enter|start|begin)\b", lower) else None)
    if start_verb:
        events.append(TrackingEvent(
            name=f"{slug}_{start_verb}", description=f"Customer {start_verb} the {label}",
            trigger=f"Customer taps the {label} entry control and the {label} renders",
            platforms=platforms, properties=[entry]))
        if re.search(r"\b(estimate|result|value|summary)\b", lower):
            events.append(TrackingEvent(
                name=f"{slug}_completed", description=f"The {label} returned a result",
                trigger=f"The {label} result is rendered to the customer (client-side)",
                platforms=platforms,
                properties=[p for p in entity_props if p.name != "plan_id"] or [entry]))
    for pattern, suffix, desc, trigger, props in _KEYWORD_EVENTS:
        if re.search(pattern, lower):
            name = f"{slug}_{suffix}"
            if suffix == "selected" and any(p.name == "plan_id" for p in entity_props):
                name = f"{slug}_plan_selected"
                props = [p for p in entity_props if p.name in ("plan_id", "monthly_price")] + props
            events.append(TrackingEvent(name=name, description=desc.format(label=label),
                                        trigger=trigger.format(label=label), platforms=platforms,
                                        properties=list(props)))
    if re.search(r"\b(service|api)\b", lower):
        events.append(TrackingEvent(
            name=f"{slug}_failed", description=f"The {label} could not load or return a result",
            trigger="Client receives an error or a timeout from the backing service",
            platforms=platforms, properties=[
                EventProperty(name="error_code", type=PropertyType.STRING,
                              description="Service or client error code"),
                EventProperty(name="failure_stage", type=PropertyType.STRING,
                              description="Step where the failure happened")]))
    # Reuse dictionary events the request names explicitly (e.g. "order placed").
    for dev in dictionary:
        if dev.status == "active" and dev.name.replace("_", " ") in lower:
            events.append(TrackingEvent(
                name=dev.name, description=dev.description or dev.name,
                trigger=f"Existing trigger (see event dictionary, owner {dev.owner or 'n/a'})",
                platforms=[p for p in dev.platforms if p in PLATFORM_VALUES] or platforms,
                properties=[EventProperty(name=n, type=_ptype(t),
                                          description="As defined in the event dictionary")
                            for n, t in dev.properties.items()],
                status="existing"))
    by_name = {d.name: d for d in dictionary}
    for ev in events:
        if ev.name in by_name and ev.status == "new":
            ev.status = "existing"
    return events


# Requirement keyword -> event suffix, most specific first.
_EVENT_FOR_REQUIREMENT = [
    (r"escalat", "_escalated"), (r"\b(rate|rating|thumbs)\b", "_feedback_submitted"),
    (r"\bskip", "_skipped"), (r"\bselect", "_selected"), (r"\bfilter", "_filter_applied"),
    (r"\bopen(s|ed)?\b", "_opened"), (r"\b(enter|start)\b", "_started"),
    (r"\b(see|estimate|value|result)\b", "_completed"), (r"\b(message|ask)\b", "_message_sent"),
    (r"\b(service|api)\b", "_failed"), (r"\b(show|page|entry point|display)\b", "_viewed"),
]


def _event_for(statement: str, events: list[TrackingEvent], slug: str) -> TrackingEvent | None:
    """The feature event that best evidences a requirement (keyword rules, specific first)."""
    s = statement.lower()
    for pattern, suffix in _EVENT_FOR_REQUIREMENT:
        if re.search(pattern, s):
            for ev in events:
                if ev.name.startswith(slug) and ev.name.endswith(suffix):
                    return ev
    return None


def mock_draft(ext: Extraction, request: str, dictionary: list[DictionaryEvent]) -> SpecContent:
    ids = _Ids()
    text = request
    lower = text.lower()
    label = re.sub(r"^(add|adding|a|an|the)\s+", "", ext.title, flags=re.I)
    label = " ".join(w if w.isupper() else w.lower() for w in label.split())
    short_label = _short_label(ext.title)
    persona = ext.personas[0] if ext.personas else "Nimbus Wireless customer"
    platforms = list(ext.platforms) or ["app", "web"]
    surface = " or ".join(platforms)
    facts = {c: [f for f in ext.facts if f.category == c] for c in
             ("requirement", "goal", "non_goal", "constraint", "metric", "context", "dependency")}

    assumptions: list[Assumption] = []

    def assume(statement: str, validate_with: str) -> str:
        aid = f"A-{len(assumptions) + 1}"
        assumptions.append(Assumption(id=aid, statement=statement, validate_with=validate_with))
        return aid

    open_questions = [OpenQuestion(id=f"OQ-{i}", question=a.question,
                                   why_it_matters=a.why_it_matters,
                                   suggested_owner=_owner_for(a.question + a.topic),
                                   blocking=bool(a.topic == "Approval"
                                                 or _ELIGIBILITY.search(a.question)))
                      for i, a in enumerate(ext.ambiguities, 1)]

    def oq_for(*keywords: str) -> str | None:
        for q in open_questions:
            if any(k.lower() in q.question.lower() for k in keywords):
                return q.id
        return None

    # Instrumentation keywords come from what the request asks for, not from background prose.
    ask_text = " ".join(f.statement for c in ("requirement", "metric", "constraint")
                        for f in facts[c])
    events = _build_events(ext, ask_text, dictionary, short_label)
    slug = ext.feature_slug

    # Requirements: every input requirement/constraint/metric sentence becomes FR or NFR verbatim.
    frs: list[Requirement] = []
    nfrs: list[Requirement] = []
    for fact in facts["requirement"] + facts["constraint"] + facts["metric"]:
        nfr_cat = _is_nfr(fact.statement)
        priority = ("must" if re.search(r"\b(must|never)\b", fact.statement, re.I)
                    else "could" if re.search(r"\b(could|nice to have|optional)\b",
                                              fact.statement, re.I) else "should")
        if nfr_cat:
            nfrs.append(Requirement(id=ids.next("NFR"), description=fact.statement,
                                    priority=priority, category=nfr_cat, refs=[fact.id]))
        else:
            cat = "analytics" if fact.category in ("metric", "constraint") else "functional"
            frs.append(Requirement(id=ids.next("FR"), description=fact.statement,
                                   priority=priority, category=cat, refs=[fact.id]))
    a_access = assume("Accessibility follows the company default of WCAG 2.1 AA.", "UX Design")
    nfrs.append(Requirement(
        id=ids.next("NFR"), category="accessibility", priority="must", source="assumption",
        description=f"All new UI on {surface} meets WCAG 2.1 AA (screen-reader labels, 4.5:1 "
                    "contrast, full keyboard/switch access).", refs=[a_access]))
    a_pii = assume("Analytics events must not carry PII; this is standard instrumentation policy.",
                   "Privacy / Analytics governance")
    nfrs.append(Requirement(
        id=ids.next("NFR"), category="privacy", priority="must", source="assumption",
        description="Tracking events contain zero PII: no names, phone numbers, free-text "
                    "message content or full account/card numbers.", refs=[a_pii]))

    # Link events back to requirements.
    for req in [r for r in frs if r.category == "functional"]:
        ev = _event_for(req.description, events, slug)
        if ev and req.id not in ev.related_requirements:
            ev.related_requirements.append(req.id)

    # User stories with Given/When/Then.
    stories: list[UserStory] = []
    goal_text = facts["goal"][0].statement.rstrip(".") if facts["goal"] else None
    events_in_acs: set[str] = set()
    for req in [r for r in frs if r.category == "functional"][:6]:
        action = _customer_action(req.description)
        then = _present_tense(req.description)
        when = f"they {action}" if action else f"they use the {short_label}"
        if action and (m := re.search(r"\s+and (?:see|view)\s+(.+)$", action)):
            when = f"they {action[:m.start()]}"
            then = f"{m.group(1)} is displayed"
        acs = [AcceptanceCriterion(given=f"a signed-in {persona} on {surface}", when=when,
                                   then=then)]
        ev = _event_for(req.description, events, slug)
        if ev and ev.name not in events_in_acs and not ev.name.endswith("_failed"):
            events_in_acs.add(ev.name)
            acs.append(AcceptanceCriterion(
                given="analytics is enabled for the session", when=when,
                then=f"`{ev.name}` fires exactly once with all required properties"))
        stories.append(UserStory(
            id=ids.next("US"), as_a=persona, i_want=_i_want(req.description),
            so_that=(f"it supports the goal: {goal_text[0].lower() + goal_text[1:]}"
                     if goal_text else "the request's intent is met (value TBD)"),
            priority=req.priority, acceptance_criteria=acs))

    # Success metrics.
    terminal = next((e.name for e in events if e.name == "order_placed"), None) or next(
        (e.name for e in events if e.name.endswith(("_completed", "_selected"))), events[0].name)
    opener = next((e.name for e in events if e.name.endswith(("_opened", "_started"))), None)
    viewed = events[0].name
    metrics: list[SuccessMetric] = []
    for goal in facts["goal"]:
        g = goal.statement
        target = (f"TBD ({oq})" if (oq := oq_for(g[:40])) else "TBD")
        if re.search(r"\b(calls?|care|contacts?)\b", g, re.I):
            ds = oq_for("care-contact") or ""
            metrics.append(SuccessMetric(
                name=g, target=target, events=[viewed],
                definition=f"Care contacts on this topic per 1,000 customers who fired `{viewed}`"
                           f" (care data source TBD{', ' + ds if ds else ''})."))
        elif re.search(r"without an agent|resolved", g, re.I) and opener:
            esc = next((e.name for e in events if e.name.endswith("_escalated")), None)
            metrics.append(SuccessMetric(
                name=g, target=target, events=[opener] + ([esc] if esc else []),
                definition=f"1 - (sessions with `{esc}` ÷ sessions with `{opener}`)" if esc
                else f"Sessions with `{opener}` and no agent contact ÷ all `{opener}` sessions"))
        elif re.search(r"\b(one funnel|both platforms|app and web)\b", g, re.I):
            metrics.append(SuccessMetric(
                name=g, target=target, events=[viewed, terminal],
                definition=f"Share of `{viewed}` → `{terminal}` funnel volume reported from "
                           "identical event names on app and web (split by `platform`); 100% when "
                           "no platform-specific events remain"))
        elif re.search(r"\b(conversion|completion)\b", g, re.I):
            metrics.append(SuccessMetric(
                name=g, target=target, events=[viewed, terminal],
                definition=f"Sessions with `{terminal}` ÷ sessions with `{viewed}`, split by "
                           "platform"))
        else:
            metrics.append(SuccessMetric(name=g, target=target, events=[viewed],
                                         definition=f"Sessions with `{viewed}` (baseline TBD)"))

    # Dependencies, API and data model changes.
    dependencies: list[Dependency] = []
    for match in _DEPENDENCY.finditer(text):
        name = match.group(0).strip()
        if any(d.name == name for d in dependencies):
            continue
        dtype = ("legal" if name in ("Legal", "Compliance", "Privacy") else "service"
                 if re.search(r"(Service|API|Platform|Catalog)$", name) else "team")
        quote = next((f.source_quote for f in ext.facts if name in f.source_quote), name)
        dependencies.append(Dependency(name=name, type=dtype, description=quote.rstrip(".")))
    dependencies.append(Dependency(name="Analytics / event dictionary owners", type="team",
                                   source="assumption",
                                   description="Review new and modified events before release."))
    api_changes: list[ApiChange] = []
    services = [d for d in dependencies if d.type == "service"]
    if services:
        a_api = assume("API contracts below are placeholders until the owning team confirms them.",
                       "Owning engineering teams")
    for dep in services:
        resource = to_snake_case(re.sub(r"\b(Service|API)\b", "", dep.name)).replace("_", "-")
        api_changes.append(ApiChange(
            method="GET", path=f"/v1/{resource or slug.replace('_', '-')}", change_type="add",
            description=f"PROPOSED client-facing read endpoint backed by {dep.name} "
                        f"({a_api}); confirm contract, auth and caching."))
    new_events = [e.name for e in events if e.status != "existing"]
    data_changes = [DataModelChange(
        entity="Event dictionary", change_type="add", fields=new_events,
        description="Register the new tracking events and their property schemas.")]

    # Edge cases (proposed expected behaviour).
    edge: list[EdgeCase] = []

    def ec(scenario: str, behaviour: str) -> None:
        edge.append(EdgeCase(id=ids.next("EC"), scenario=scenario, expected_behavior=behaviour))

    for dep in services:
        ec(f"{dep.name} times out or returns an error",
           f"Show a non-blocking error state, let the customer continue, and fire `{slug}_failed` "
           "with error_code.")
    if re.search(r"\bskip", lower):
        ec("Customer skips the step, then navigates back to it",
           "The step is shown again with nothing pre-applied; no duplicate credit is created.")
    if m := re.search(r"up to (\d+)", lower):
        ec(f"Customer tries to select more than {m.group(1)} items",
           f"Selection beyond {m.group(1)} is blocked with an inline message.")
    if re.search(r"\bfilter", lower):
        ec("A filter combination returns no results", "Show an empty state with a reset action.")
    if re.search(r"\b(card|bank account)\b", lower):
        ec("Customer types a full card or bank number into the chat",
           "The number is masked in the transcript and never sent to analytics.")
    for q in open_questions:
        if _ELIGIBILITY.search(q.question):
            ec(f"Customer in a group whose eligibility is unresolved ({q.id}: {q.question})",
               f"Behaviour follows the answer to {q.id}; until it is resolved the feature stays "
               "hidden for that group.")
    if len(platforms) > 1:
        ec("Customer starts on app and finishes on web (or vice versa)",
           "Same content on both; events keep identical names and differ only in `platform`.")
    ec("Analytics is blocked or consent is declined",
       "The feature works normally; no events are sent and no errors are shown.")

    # Rollout & experiment.
    flag = f"{slug}_enabled"
    a_roll = assume("Rollout stages follow the standard flag-based ramp.", "Release management")
    exp = None
    if re.search(r"\b(a/b|experiment)\b", lower):
        exp_oq = oq_for("experiment")
        primary = metrics[0].name if metrics else f"`{terminal}` rate"
        exp = Experiment(
            hypothesis=f"Exposing the {label} improves: {primary}.",
            variants=["control: current experience", f"treatment: {label}"],
            randomization_unit="customer account (all lines on an account see the same variant)",
            primary_metric=primary,
            guardrail_metrics=[f"`{slug}_failed` rate" if services else "error rate",
                               "care contact rate"],
            minimum_detectable_effect=f"TBD ({exp_oq})" if exp_oq else "TBD")
    rollout = RolloutPlan(
        feature_flag=flag, experiment=exp, source="assumption",
        rollback_plan=f"Turn off `{flag}`; customers fall back to the current experience. "
                      f"Basis: {a_roll}.",
        phases=[
            RolloutPhase(name="Internal dogfood", audience="Employee and test accounts",
                         exposure_percent=0, exit_criteria="No P1/P2 defects; all events "
                                                           "validated in the analytics debugger"),
            RolloutPhase(name="Pilot", audience=f"{persona}s on {surface}", exposure_percent=5,
                         exit_criteria="Error rate and care contacts at or below baseline for "
                                       "7 days"),
            RolloutPhase(name="Ramp", audience="Same", exposure_percent=50,
                         exit_criteria="Primary metric not worse than control"),
            RolloutPhase(name="General availability", audience="All eligible customers",
                         exposure_percent=100, exit_criteria="Experiment readout signed off"),
        ])

    # Test plan.
    tests: list[TestCase] = []
    story_for = {}
    for s in stories:
        for r in frs:
            if _i_want(r.description) == s.i_want:
                story_for[r.id] = s
    for req in frs + nfrs:
        story = story_for.get(req.id)
        steps = ([f"Given {story.acceptance_criteria[0].given}",
                  f"When {story.acceptance_criteria[0].when}"] if story
                 else ["Set up a test account with the feature flag on",
                       f"Exercise the behaviour in {req.id}"])
        ttype = ("accessibility" if req.category == "accessibility" else "analytics"
                 if req.category in ("analytics", "privacy") else "performance"
                 if req.category.startswith("performance") else "e2e")
        tests.append(TestCase(
            id=ids.next("TC"), title=f"Verify {req.id}", type=ttype, steps=steps,
            expected_result=(_sentence_case(story.acceptance_criteria[0].then) if story
                             else _present_tense(req.description)[0].upper()
                             + _present_tense(req.description)[1:]),
            covers=[req.id] + ([story.id] if story else [])))
    for ev in events:
        tests.append(TestCase(
            id=ids.next("TC"), title=f"Analytics: `{ev.name}` payload", type="analytics",
            steps=[f"Trigger: {ev.trigger}",
                   f"Inspect the event in the analytics debugger on {', '.join(ev.platforms)}"],
            expected_result="Fires exactly once with global properties and: "
                            + (", ".join(p.name for p in ev.properties) or "no extra properties")
                            + "; values match the UI.",
            covers=list(ev.related_requirements), events_verified=[ev.name]))

    # Risks.
    risks = [Risk(description="Event names drift between app and web, breaking the cross-platform "
                              "funnel", likelihood="medium", impact="high",
                  mitigation="Treat section 7 as the single source; lint against the event "
                             "dictionary in CI.")]
    for dep in services:
        risks.append(Risk(description=f"{dep.name} latency or outage degrades the experience",
                          likelihood="medium", impact="medium",
                          mitigation="Timeouts with graceful fallback; alert on the failed-event "
                                     "rate."))
    if any(d.type == "legal" for d in dependencies):
        risks.append(Risk(description="Legal review changes what data can be used", likelihood=
                          "medium", impact="high", mitigation="Start review now; design for the "
                                                              "minimal data set."))
    if open_questions:
        risks.append(Risk(description=f"{sum(q.blocking for q in open_questions)} blocking open "
                                      "question(s) delay build start", likelihood="high",
                          impact="medium", mitigation="Review open questions with owners before "
                                                      "sprint planning."))
    if exp:
        risks.append(Risk(description="Experiment is under-powered for the expected effect",
                          likelihood="medium", impact="medium",
                          mitigation="Size the test once the MDE is agreed."))

    first_ask = facts["requirement"][0].statement if facts["requirement"] else ext.summary
    overview = (f"{ext.title} for {persona}s on {surface}. Headline ask: {first_ask} This spec "
                f"captures {len(frs)} functional and {len(nfrs)} non-functional requirements, "
                f"{len(events)} tracking events, the rollout and test plan, and the open questions the "
                "request leaves unanswered (section 15).")
    problem = " ".join(f.statement for f in facts["context"]) or ext.summary
    return SpecContent(
        title=ext.title, overview=overview, problem_statement=problem,
        goals=[f.statement for f in facts["goal"]],
        non_goals=[f.statement.rstrip(".") for f in facts["non_goal"]],
        user_stories=stories, functional_requirements=frs, non_functional_requirements=nfrs,
        analytics=AnalyticsPlan(global_properties=_global_properties(), events=events,
                                success_metrics=metrics),
        data_model_changes=data_changes, api_changes=api_changes, dependencies=dependencies,
        edge_cases=edge, rollout=rollout, test_plan=tests, risks=risks, assumptions=assumptions,
        open_questions=open_questions)


# ---------------------------------------------------------------------------------------------
# Stage (c): critique
# ---------------------------------------------------------------------------------------------

_RUBRIC_FROM_CATEGORY = {
    "completeness": "Section completeness",
    "testability": "Requirement quality",
    "instrumentation": "Tracking plan",
    "traceability": "Consistency & traceability",
    "ambiguity_handling": "Ambiguity handling",
    "clarity": "User stories & acceptance criteria",
}


def mock_critique(score: ScoreReport, lint: LintReport | None) -> Critique:
    by_name = {c.name: c for c in score.categories}
    rubric = {k: max(1, round(5 * by_name[v].score / by_name[v].max_score))
              for k, v in _RUBRIC_FROM_CATEGORY.items()}
    sev = {"error": "major", "warning": "minor", "info": "info"}
    issues = [CritiqueIssue(section=f.location, severity=sev[f.severity], issue=f.message,  # type: ignore[arg-type]
                            suggestion="Fix as described.")
              for c in score.categories for f in c.findings if f.severity != "info"]
    # Lint findings arrive inside the score report (tracking-plan category); add their fixes.
    suggestions = {(lf.event, lf.rule): lf.suggestion for lf in (lint.findings if lint else [])}
    for issue in issues:
        m = re.match(r"\[dictionary:([\w-]+)\]", issue.issue)
        if m and (issue.section, m.group(1)) in suggestions:
            issue.suggestion = suggestions[(issue.section, m.group(1))]
    return Critique(rubric_scores=rubric, issues=issues,
                    summary=f"{len(issues)} issues from the deterministic rubric and event linter.")


# ---------------------------------------------------------------------------------------------
# Stage (d): revise
# ---------------------------------------------------------------------------------------------


_COMPOUND_SPLIT = re.compile(
    r",?\s+and\s+(?=(?:the|a|an)\s+[\w-]+(?:\s+[\w-]+)?\s+(?:must|should|shall|will)\b)", re.I)


def _sentence_case(text: str) -> str:
    return text[:1].upper() + text[1:]


def _rename_event(spec: SpecContent, old: str, new: str) -> None:
    for ev in spec.analytics.events:
        if ev.name == old:
            ev.name = new
    for m in spec.analytics.success_metrics:
        m.events = [new if e == old else e for e in m.events]
        m.definition = m.definition.replace(f"`{old}`", f"`{new}`")
    for t in spec.test_plan:
        t.events_verified = [new if e == old else e for e in t.events_verified]
        t.title = t.title.replace(f"`{old}`", f"`{new}`")
    for s in spec.user_stories:
        for ac in s.acceptance_criteria:
            ac.then = ac.then.replace(f"`{old}`", f"`{new}`")
    for ec in spec.edge_cases:
        ec.expected_behavior = ec.expected_behavior.replace(f"`{old}`", f"`{new}`")
    for dm in spec.data_model_changes:
        dm.fields = [f for f in dm.fields if f != old]


def mock_revise(draft: SpecContent, lint: LintReport | None,
                dictionary: list[DictionaryEvent]) -> SpecContent:
    spec = draft.model_copy(deep=True)
    oq_ids = [int(q.id.split("-")[1]) for q in spec.open_questions]
    counter = {"oq": max(oq_ids, default=0)}

    def add_oq(question: str, why: str, owner: str, blocking: bool = False) -> str:
        for q in spec.open_questions:
            if q.question == question:
                return q.id
        counter["oq"] += 1
        qid = f"OQ-{counter['oq']}"
        spec.open_questions.append(OpenQuestion(id=qid, question=question, why_it_matters=why,
                                                suggested_owner=owner, blocking=blocking))
        return qid

    # 1a. Split compound requirements ("X should A and Y should B") into atomic ones.
    for reqs in (spec.functional_requirements, spec.non_functional_requirements):
        prefix = "NFR" if reqs is spec.non_functional_requirements else "FR"
        next_id = max((int(r.id.split("-")[1]) for r in reqs), default=0)
        for req in list(reqs):
            parts = _COMPOUND_SPLIT.split(req.description.rstrip("."))
            if len(parts) < 2:
                continue
            req.description = parts[0].strip() + "."
            for t in spec.test_plan:
                if t.covers == [req.id]:
                    t.expected_result = _sentence_case(_present_tense(req.description))
            for part in parts[1:]:
                next_id += 1
                reqs.append(req.model_copy(update={
                    "id": f"{prefix}-{next_id}", "refs": list(req.refs),
                    "description": _sentence_case(part.strip()) + "."}))

    # 1b. Vague / unmeasurable requirements -> link (or raise) an open question.
    for req in spec.functional_requirements + spec.non_functional_requirements:
        if OPEN_QUESTION_REF_RE.search(req.description):
            continue
        vague = find_vague_terms(req.description)
        unmeasurable = (req.id.startswith("NFR")
                        and not re.search(r"\d|\b(never|must not|always|zero|none)\b",
                                          req.description, re.I))
        if not (vague or unmeasurable):
            continue
        existing = next((q.id for q in spec.open_questions
                         if req.description.rstrip(".").lower() in q.question.lower()), None)
        qid = existing or add_oq(
            f"What measurable target applies to {req.id} (\"{req.description.rstrip('.')}\")?",
            "Without a threshold the requirement cannot be tested or accepted.",
            _owner_for(req.description))
        terms = ", ".join(f"'{v}'" for v in vague) or "threshold"
        req.description = f"{req.description.rstrip('.')} [measurable target for {terms} TBD: {qid}]."
        req.refs.append(qid)

    # 2. Event-linter findings.
    by_name = {d.name: d for d in dictionary}
    for f in (lint.findings if lint else []):
        ev = next((e for e in spec.analytics.events if e.name == f.event), None)
        if ev is None:
            continue
        if f.rule == "naming-drift" and f.dictionary_match:
            match = by_name[f.dictionary_match]
            if match.name == to_snake_case(match.name):
                _rename_event(spec, ev.name, match.name)
                ev.status = "modified"
            else:
                add_oq(f"Should legacy event `{match.name}` be migrated to `{ev.name}`?",
                       "Keeping both names splits historical and new data.", "Analytics")
        elif f.rule in ("duplicate-event", "existing-event-changed"):
            match = by_name.get(ev.name)
            changed = match and (set(ev.platforms) - set(match.platforms)
                                 or {p.name for p in ev.properties} - set(match.properties))
            ev.status = "modified" if changed else "existing"
        elif f.rule in ("possible-duplicate", "synonym-drift") and f.dictionary_match:
            add_oq(f"Is `{ev.name}` the same user action as existing `{f.dictionary_match}`? If "
                   "so, reuse the existing event.", "Avoids two events for one action, which "
                                                    "double-counts the funnel.", "Analytics")
        elif f.rule == "property-type-conflict":
            add_oq(f"{f.message} Align the type or version the property?",
                   "Conflicting types break joins and dashboards across events.", "Analytics")
        elif f.rule == "deprecated-event":
            add_oq(f"`{ev.name}` is deprecated: which event replaces it?",
                   "New instrumentation must not use deprecated events.", "Analytics", True)
    new_names = {e.name for e in spec.analytics.events if e.status == "new"}
    for dm in spec.data_model_changes:
        if dm.entity == "Event dictionary":
            dm.fields = sorted(new_names)
            dm.description = ("Register the new tracking events; update the modified ones: "
                              + (", ".join(e.name for e in spec.analytics.events
                                           if e.status == "modified") or "none") + ".")

    # 3. Consistency: drop dangling references, add missing tests.
    names = {e.name for e in spec.analytics.events}
    ids = {r.id for r in spec.functional_requirements + spec.non_functional_requirements} | {
        s.id for s in spec.user_stories}
    for t in spec.test_plan:
        t.events_verified = [e for e in t.events_verified if e in names]
        t.covers = [c for c in t.covers if c in ids]
    for m in spec.analytics.success_metrics:
        m.events = [e for e in m.events if e in names]
    next_tc = max((int(t.id.split("-")[1]) for t in spec.test_plan), default=0)
    covered = {c for t in spec.test_plan for c in t.covers}
    verified = {e for t in spec.test_plan for e in t.events_verified}
    for req in spec.functional_requirements + spec.non_functional_requirements:
        if req.id not in covered:
            next_tc += 1
            ttype = "e2e" if req.id.startswith("FR") else "performance"
            spec.test_plan.append(TestCase(id=f"TC-{next_tc}", title=f"Verify {req.id}", type=ttype,
                                           steps=[f"Exercise the behaviour in {req.id}"],
                                           expected_result=_sentence_case(
                                               _present_tense(req.description)),
                                           covers=[req.id]))
    for ev in spec.analytics.events:
        if ev.name not in verified:
            next_tc += 1
            spec.test_plan.append(TestCase(
                id=f"TC-{next_tc}", title=f"Analytics: `{ev.name}` payload", type="analytics",
                steps=[f"Trigger: {ev.trigger}"], events_verified=[ev.name],
                expected_result="Fires once with all required properties."))

    # 4. Gaps the input does not answer become questions, never invented content.
    if not spec.non_goals:
        add_oq("What is explicitly out of scope for this release?",
               "Unstated non-goals cause scope creep during build.", "Product")
    for story in spec.user_stories:
        if not story.acceptance_criteria:
            story.acceptance_criteria.append(AcceptanceCriterion(
                given="the feature flag is on", when=f"the customer tries to {story.i_want}",
                then="the outcome described in the linked requirement is observed"))
    return spec


# ---------------------------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------------------------


class MockLLM:
    """Offline client with the same interface as ``LiteLLMClient``."""

    model = "mock"
    offline = True

    def __init__(self) -> None:
        self.usage = UsageTracker()

    def structured(self, stage: str, messages: list[dict[str, str]], response_model: type[T],
                   context: dict[str, Any]) -> T:
        self.usage.stages.append(StageUsage(stage=stage, attempts=1))
        dictionary = context.get("dictionary") or []
        if stage == "extract":
            out: BaseModel = mock_extract(context["request"], context.get("context_docs") or {},
                                          dictionary)
        elif stage == "draft":
            out = mock_draft(context["extraction"], context["request"], dictionary)
        elif stage == "critique":
            out = mock_critique(context["score"], context.get("lint"))
        elif stage == "revise":
            out = mock_revise(context["draft"], context.get("lint"), dictionary)
        else:
            raise ValueError(f"MockLLM has no rule set for stage '{stage}'")
        # Round-trip through the requested model: the mock obeys the same schema as a real LLM.
        return response_model.model_validate(out.model_dump())
