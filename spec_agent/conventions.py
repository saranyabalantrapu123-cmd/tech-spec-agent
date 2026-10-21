"""Shared spec-writing and analytics-instrumentation conventions.

One place for the rules the scorer, the event linter, the MockLLM and the LLM prompts all agree on,
so "what good looks like" cannot drift between generation and evaluation.
"""

from __future__ import annotations

import re

# --- Tracking-plan conventions --------------------------------------------------------------

EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
PROPERTY_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
MAX_EVENT_NAME_LEN = 50

# Last token of an event name must be one of these past-tense actions (<object>_<action>).
APPROVED_ACTIONS: frozenset[str] = frozenset(
    {
        "added", "applied", "clicked", "closed", "collapsed", "completed", "dismissed",
        "downloaded", "errored", "escalated", "expanded", "failed", "loaded", "opened", "placed",
        "received", "removed", "requested", "returned", "saved", "searched", "selected", "sent",
        "shared", "shown", "skipped", "started", "submitted", "succeeded", "tapped", "toggled",
        "updated", "viewed",
    }
)

# Properties every event must carry (declared once under analytics.global_properties, or per event).
REQUIRED_GLOBAL_PROPERTIES: dict[str, str] = {
    "platform": "Surface the event fired on (app or web)",
    "brand": "Brand the customer account belongs to",
    "session_id": "Analytics session identifier",
}
PLATFORM_VALUES = ["app", "web"]
BRAND_VALUES = ["nimbus_wireless", "nimbus_prepaid"]

# Synonyms that commonly cause naming drift between teams (normalised to the first form).
ACTION_SYNONYMS: dict[str, str] = {
    "view": "viewed", "viewed": "viewed", "impression": "viewed", "shown": "viewed",
    "displayed": "viewed", "seen": "viewed",
    "click": "clicked", "clicked": "clicked", "tap": "clicked", "tapped": "clicked",
    "press": "clicked", "pressed": "clicked",
    "open": "opened", "opened": "opened", "launch": "opened", "launched": "opened",
    "select": "selected", "selected": "selected", "choose": "selected", "chosen": "selected",
    "pick": "selected", "picked": "selected",
    "submit": "submitted", "submitted": "submitted", "send": "submitted", "sent": "submitted",
    "start": "started", "started": "started", "begin": "started", "began": "started",
    "complete": "completed", "completed": "completed", "finish": "completed",
    "finished": "completed", "succeeded": "completed",
    "fail": "failed", "failed": "failed", "error": "failed", "errored": "failed",
}
OBJECT_SYNONYMS: dict[str, str] = {
    "estimate": "quote", "quote": "quote", "valuation": "quote",
    "compare": "comparison", "comparison": "comparison",
    "assistant": "assistant", "bot": "assistant", "chatbot": "assistant",
    "bill": "bill", "invoice": "bill", "statement": "bill",
}

# --- Requirement-quality conventions ----------------------------------------------------------

# Words/phrases that make a requirement untestable unless they are tied to a measurable target.
VAGUE_TERMS: tuple[str, ...] = (
    "fast", "quick", "quickly", "easy", "easily", "simple", "simply", "user-friendly",
    "user friendly", "intuitive", "seamless", "seamlessly", "robust", "efficient", "efficiently",
    "flexible", "scalable", "optimal", "optimize", "minimal", "as needed", "as appropriate",
    "if possible", "etc", "and so on", "and/or", "better", "best-in-class", "modern", "nice",
    "smooth", "clean", "some", "several", "many", "a lot", "appropriate", "reasonable",
)
_VAGUE_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(t) for t in sorted(VAGUE_TERMS, key=len, reverse=True))
    + r")(?![\w-])",
    re.IGNORECASE,
)

REQ_ID_RE = {"FR": re.compile(r"^FR-\d+$"), "NFR": re.compile(r"^NFR-\d+$")}
OPEN_QUESTION_REF_RE = re.compile(r"\bOQ-\d+\b")


def find_vague_terms(text: str) -> list[str]:
    """Return the vague terms in ``text`` (lower-cased, de-duplicated, in order of appearance)."""
    seen: list[str] = []
    for match in _VAGUE_RE.finditer(text):
        term = match.group(1).lower()
        if term not in seen:
            seen.append(term)
    return seen


def to_snake_case(text: str) -> str:
    """Convert ``'Plan Compare-Select'`` / ``'planCompareSelect'`` to ``'plan_compare_select'``."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return text.strip("_").lower()
