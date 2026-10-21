"""Deterministic (no-LLM) spec quality scorer.

Scores a ``TechSpec`` out of 100 across six weighted categories and returns itemised findings,
so every point lost can be traced to a concrete fix. Same input -> same score, which makes it
usable as a CI gate and as the objective half of the evaluation harness.
"""

from __future__ import annotations

import re
from typing import Callable

from .conventions import (
    APPROVED_ACTIONS,
    EVENT_NAME_RE,
    MAX_EVENT_NAME_LEN,
    OPEN_QUESTION_REF_RE,
    PROPERTY_NAME_RE,
    REQ_ID_RE,
    REQUIRED_GLOBAL_PROPERTIES,
    find_vague_terms,
)
from .linter import LintReport
from .schema import CategoryScore, Finding, PropertyType, Requirement, ScoreReport, TechSpec

WEIGHTS = {
    "Section completeness": 20,
    "User stories & acceptance criteria": 15,
    "Requirement quality": 20,
    "Tracking plan": 20,
    "Consistency & traceability": 15,
    "Ambiguity handling": 10,
}

# A threshold is measurable if it has a number or is an absolute, binary rule ("never", "must not").
_MEASURABLE_RE = re.compile(r"\d|\b(never|must not|always|zero|none)\b", re.IGNORECASE)


_MODAL_RE = re.compile(r"\b(must|should|shall|will)\b", re.IGNORECASE)
LINT_PENALTY = {"error": 1.0, "warning": 0.5, "info": 0.0}
MAX_LINT_PENALTY = 6.0


def _frac(passed: int, total: int) -> float:
    return passed / total if total else 0.0


def _non_empty(text: str | None, min_words: int = 2) -> bool:
    return bool(text) and len(text.split()) >= min_words


# --- categories --------------------------------------------------------------------------------


def _completeness(spec: TechSpec) -> tuple[float, list[Finding]]:
    sections: dict[str, bool] = {
        "Overview": _non_empty(spec.overview, 5),
        "Problem statement": _non_empty(spec.problem_statement, 5),
        "Goals": bool(spec.goals),
        "Non-goals": bool(spec.non_goals),
        "User stories": bool(spec.user_stories),
        "Functional requirements": bool(spec.functional_requirements),
        "Non-functional requirements": bool(spec.non_functional_requirements),
        "Tracking events": bool(spec.analytics.events),
        "Success metrics": bool(spec.analytics.success_metrics),
        "Data model / API changes": bool(spec.data_model_changes or spec.api_changes),
        "Dependencies": bool(spec.dependencies),
        "Edge cases": bool(spec.edge_cases),
        "Rollout plan": spec.rollout is not None and bool(spec.rollout.phases),
        "Test plan": bool(spec.test_plan),
        "Risks": bool(spec.risks),
        "Open questions": bool(spec.open_questions),
    }
    findings = [
        Finding(severity="error", location=name, message="Section is missing or empty.")
        for name, ok in sections.items() if not ok
    ]
    return _frac(sum(sections.values()), len(sections)), findings


def _stories(spec: TechSpec) -> tuple[float, list[Finding]]:
    findings: list[Finding] = []
    if not spec.user_stories:
        return 0.0, [Finding(severity="error", location="User stories", message="No user stories.")]
    passed = 0
    seen: set[str] = set()
    for story in spec.user_stories:
        ok = True
        loc = story.id
        if not re.fullmatch(r"US-\d+", story.id) or story.id in seen:
            findings.append(Finding(severity="warning", location=loc,
                                    message="Story ID must be unique and look like US-<n>."))
            ok = False
        seen.add(story.id)
        if not _non_empty(story.so_that, 3):
            findings.append(Finding(severity="warning", location=loc,
                                    message="'So that' (the user value) is missing."))
            ok = False
        if not story.acceptance_criteria:
            findings.append(Finding(severity="error", location=loc,
                                    message="Story has no acceptance criteria."))
            ok = False
        for i, ac in enumerate(story.acceptance_criteria, 1):
            if not all(_non_empty(x, 2) for x in (ac.given, ac.when, ac.then)):
                findings.append(Finding(severity="error", location=f"{loc} AC{i}",
                                        message="Acceptance criterion is not a full "
                                                "Given/When/Then."))
                ok = False
            vague = find_vague_terms(ac.then)
            if vague and not OPEN_QUESTION_REF_RE.search(ac.then):
                findings.append(Finding(severity="warning", location=f"{loc} AC{i}",
                                        message=f"'Then' clause is not verifiable: "
                                                f"{', '.join(vague)}."))
                ok = False
        passed += ok
    return _frac(passed, len(spec.user_stories)), findings


def _requirement_checks(req: Requirement, kind: str, seen: set[str],
                        assumption_ids: set[str]) -> list[Finding]:
    out: list[Finding] = []
    if not REQ_ID_RE[kind].match(req.id) or req.id in seen:
        out.append(Finding(severity="error", location=req.id or "(no id)",
                           message=f"Requirement ID must be unique and look like {kind}-<n>."))
    seen.add(req.id)
    vague = find_vague_terms(req.description)
    deferred = bool(OPEN_QUESTION_REF_RE.search(req.description + " " + " ".join(req.refs)))
    if vague and not deferred:
        out.append(Finding(severity="error", location=req.id,
                           message=f"Untestable wording: {', '.join(repr(v) for v in vague)}. "
                                   "Replace with a measurable target or link an open question."))
    elif vague:
        out.append(Finding(severity="info", location=req.id,
                           message=f"Vague wording ({', '.join(vague)}) is deferred to an open "
                                   "question; resolve before build."))
    if len(_MODAL_RE.findall(req.description)) >= 2:
        out.append(Finding(severity="warning", location=req.id,
                           message="Combines several requirements in one statement; split it so "
                                   "each can be tested and prioritised separately."))
    if kind == "NFR" and not (_MEASURABLE_RE.search(req.description) or deferred):
        out.append(Finding(severity="error", location=req.id,
                           message="Non-functional requirement has no measurable threshold."))
    if req.source == "assumption" and not any(r in assumption_ids for r in req.refs):
        out.append(Finding(severity="error", location=req.id,
                           message="Requirement is an assumption but does not reference an "
                                   "Assumption (A-n)."))
    return out


def _requirements(spec: TechSpec) -> tuple[float, list[Finding]]:
    if not spec.functional_requirements:
        return 0.0, [Finding(severity="error", location="Functional requirements",
                             message="No functional requirements.")]
    assumption_ids = {a.id for a in spec.assumptions}
    seen: set[str] = set()
    findings: list[Finding] = []
    passed = total = 0
    for kind, reqs in (("FR", spec.functional_requirements),
                       ("NFR", spec.non_functional_requirements)):
        for req in reqs:
            total += 1
            res = _requirement_checks(req, kind, seen, assumption_ids)
            findings.extend(res)
            passed += not any(f.severity != "info" for f in res)
    return _frac(passed, total), findings


def _tracking(spec: TechSpec) -> tuple[float, list[Finding]]:
    events = spec.analytics.events
    if not events:
        return 0.0, [Finding(severity="error", location="Tracking plan",
                             message="No tracking events defined.")]
    findings: list[Finding] = []
    global_names = {p.name for p in spec.analytics.global_properties}
    missing_globals = [g for g in REQUIRED_GLOBAL_PROPERTIES if g not in global_names]
    passed = 0
    seen: set[str] = set()
    for ev in events:
        problems: list[str] = []
        if not EVENT_NAME_RE.match(ev.name):
            problems.append("name is not snake_case <object>_<action>")
        elif ev.name.split("_")[-1] not in APPROVED_ACTIONS:
            problems.append(f"action '{ev.name.split('_')[-1]}' is not an approved past-tense verb")
        if len(ev.name) > MAX_EVENT_NAME_LEN:
            problems.append(f"name longer than {MAX_EVENT_NAME_LEN} characters")
        if ev.name in seen:
            problems.append("duplicate event name")
        seen.add(ev.name)
        own_props = [p for p in ev.properties if p.name not in REQUIRED_GLOBAL_PROPERTIES]
        if not own_props:
            problems.append("no event-specific properties")
        for p in ev.properties:
            if not PROPERTY_NAME_RE.match(p.name):
                problems.append(f"property '{p.name}' is not snake_case")
            if p.type == PropertyType.ENUM and not p.allowed_values:
                problems.append(f"enum property '{p.name}' has no allowed_values")
        if not _non_empty(ev.trigger, 3):
            problems.append("trigger is not described")
        if not ev.platforms:
            problems.append("no platform (app/web)")
        ev_missing = [g for g in missing_globals if g not in {p.name for p in ev.properties}]
        if ev_missing:
            problems.append(f"missing required properties: {', '.join(ev_missing)}")
        for msg in problems:
            findings.append(Finding(severity="error", location=ev.name, message=msg))
        passed += not problems
    return _frac(passed, len(events)), findings


def _consistency(spec: TechSpec) -> tuple[float, list[Finding]]:
    findings: list[Finding] = []
    event_names = {e.name for e in spec.analytics.events}
    req_ids = {r.id for r in spec.functional_requirements + spec.non_functional_requirements}
    story_ids = {s.id for s in spec.user_stories}
    known_ids = req_ids | story_ids

    verified = [(t.id, e) for t in spec.test_plan for e in t.events_verified]
    bad_verified = [(tid, e) for tid, e in verified if e not in event_names]
    for tid, e in bad_verified:
        findings.append(Finding(severity="error", location=tid,
                                message=f"Test verifies event '{e}' which is not in the tracking "
                                        "plan."))
    covers = [(t.id, c) for t in spec.test_plan for c in t.covers]
    bad_covers = [(tid, c) for tid, c in covers if c not in known_ids]
    for tid, c in bad_covers:
        findings.append(Finding(severity="error", location=tid,
                                message=f"Test covers unknown requirement/story '{c}'."))
    covered = {c for _, c in covers}
    uncovered_fr = [r.id for r in spec.functional_requirements if r.id not in covered]
    for rid in uncovered_fr:
        findings.append(Finding(severity="warning", location=rid,
                                message="Functional requirement has no test case."))
    verified_names = {e for _, e in verified}
    unverified = [e for e in event_names if e not in verified_names]
    for e in sorted(unverified):
        findings.append(Finding(severity="warning", location=e,
                                message="Tracking event is not verified by any test case."))
    metric_refs = [(m.name, e) for m in spec.analytics.success_metrics for e in m.events]
    bad_metric = [(m, e) for m, e in metric_refs if e not in event_names]
    for m, e in bad_metric:
        findings.append(Finding(severity="error", location=f"Metric: {m}",
                                message=f"Metric uses event '{e}' which is not in the tracking "
                                        "plan."))
    rel = [(e.name, r) for e in spec.analytics.events for r in e.related_requirements]
    bad_rel = [(e, r) for e, r in rel if r not in known_ids]
    for e, r in bad_rel:
        findings.append(Finding(severity="warning", location=e,
                                message=f"Event references unknown requirement '{r}'."))

    def ok_frac(bad: list, total: list) -> float:
        return 1.0 if not total else 1 - len(bad) / len(total)

    parts = [
        (4, ok_frac(bad_verified, verified) if verified else 0.0),
        (3, ok_frac(bad_covers, covers) if covers else 0.0),
        (3, ok_frac(uncovered_fr, spec.functional_requirements)),
        (2, ok_frac(unverified, list(event_names))),
        (2, ok_frac(bad_metric, metric_refs) if metric_refs else 0.0),
        (1, ok_frac(bad_rel, rel)),
    ]
    if not verified:
        findings.append(Finding(severity="error", location="Test plan",
                                message="No test case verifies any tracking event."))
    if not metric_refs:
        findings.append(Finding(severity="error", location="Success metrics",
                                message="No success metric is defined in terms of events."))
    return sum(w * f for w, f in parts) / sum(w for w, _ in parts), findings


def _ambiguity(spec: TechSpec) -> tuple[float, list[Finding]]:
    findings: list[Finding] = []
    oq_ids = {q.id for q in spec.open_questions}
    a_ids = {a.id for a in spec.assumptions}
    has_oq = bool(spec.open_questions)
    if not has_oq:
        findings.append(Finding(severity="error", location="Open questions",
                                message="No open questions: every real request leaves something "
                                        "ambiguous."))
    explained = sum(_non_empty(q.why_it_matters, 3) for q in spec.open_questions)
    for q in spec.open_questions:
        if not _non_empty(q.why_it_matters, 3):
            findings.append(Finding(severity="warning", location=q.id,
                                    message="Open question does not say why it matters."))
    assumed = [r for r in spec.functional_requirements + spec.non_functional_requirements
               if r.source == "assumption"]
    traced = sum(any(ref in a_ids for ref in r.refs) for r in assumed)
    dump = spec.model_dump_json(exclude={"open_questions"})
    refs = set(OPEN_QUESTION_REF_RE.findall(dump))
    dangling = sorted(refs - oq_ids)
    for ref in dangling:
        findings.append(Finding(severity="error", location=ref,
                                message="Referenced open question does not exist."))
    score = (
        0.4 * has_oq
        + 0.2 * (_frac(explained, len(spec.open_questions)) if has_oq else 0.0)
        + 0.2 * (_frac(traced, len(assumed)) if assumed else 1.0)
        + 0.2 * (1 - _frac(len(dangling), len(refs)) if refs else 1.0)
    )
    return score, findings


_CATEGORIES: dict[str, Callable[[TechSpec], tuple[float, list[Finding]]]] = {
    "Section completeness": _completeness,
    "User stories & acceptance criteria": _stories,
    "Requirement quality": _requirements,
    "Tracking plan": _tracking,
    "Consistency & traceability": _consistency,
    "Ambiguity handling": _ambiguity,
}


def score_spec(spec: TechSpec, lint: LintReport | None = None) -> ScoreReport:
    """Score ``spec`` out of 100 with itemised findings per category.

    When an event-dictionary ``lint`` report is supplied, unresolved lint findings are deducted
    from the tracking-plan category (1 point per error, 0.5 per warning, at most 6 points).
    """
    categories = []
    for name, fn in _CATEGORIES.items():
        fraction, findings = fn(spec)
        points = WEIGHTS[name] * fraction
        if name == "Tracking plan" and lint is not None:
            penalty = min(MAX_LINT_PENALTY, sum(LINT_PENALTY[f.severity] for f in lint.findings))
            points = max(0.0, points - penalty)
            findings += [Finding(severity=f.severity, location=f.event,
                                 message=f"[dictionary:{f.rule}] {f.message}")
                         for f in lint.findings]
        categories.append(CategoryScore(name=name, score=round(points, 1),
                                        max_score=WEIGHTS[name], findings=findings))
    return ScoreReport(total=round(sum(c.score for c in categories), 1), categories=categories)
