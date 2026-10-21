"""Evaluation harness: full pipeline (with critique + revise) vs a single-pass baseline.

For every example request it records, for both variants:
* the deterministic quality score (/100) and lint findings against the event dictionary,
* ambiguity recall against a hand-labelled gold set (``evals/expected_ambiguities.json``),
* guardrail relabels (requirements that claimed to come from the input but cited no fact),
* tokens and estimated cost when a real model is used.

    python -m spec_agent.evaluation            # offline (MockLLM) unless a key is configured
    LLM_MODEL=anthropic/claude-sonnet-4-5 ANTHROPIC_API_KEY=... python -m spec_agent.evaluation

Nothing here is hard-coded: real-model numbers only exist after you run it with a key.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .linter import load_event_dictionary
from .llm import OFFLINE_BANNER, get_client, is_offline
from .pipeline import PipelineResult, run_pipeline
from .schema import TechSpec

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUTS = ROOT / "examples" / "inputs"
DEFAULT_GOLD = ROOT / "evals" / "expected_ambiguities.json"
DEFAULT_OUT = ROOT / "evals" / "results"


@dataclass
class VariantResult:
    score: float
    categories: dict[str, float]
    lint_errors: int
    lint_warnings: int
    open_questions: int
    ambiguity_recall: float
    missed_gaps: list[str]
    guardrail_relabels: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


def ambiguity_recall(spec: TechSpec, gold: list[dict]) -> tuple[float, list[str]]:
    """Share of gold gaps that appear (by keyword) in the spec's open questions."""
    text = " ".join(f"{q.question} {q.why_it_matters}" for q in spec.open_questions).lower()
    missed = [g["gap"] for g in gold if not any(k.lower() in text for k in g["any"])]
    return (1 - len(missed) / len(gold) if gold else 0.0), missed


def _variant(result: PipelineResult, gold: list[dict]) -> VariantResult:
    recall, missed = ambiguity_recall(result.spec, gold)
    usage = result.client.usage
    return VariantResult(
        score=result.score.total,
        categories={c.name: c.score for c in result.score.categories},
        lint_errors=len(result.lint.errors) if result.lint else 0,
        lint_warnings=len(result.lint.warnings) if result.lint else 0,
        open_questions=len(result.spec.open_questions),
        ambiguity_recall=round(recall, 3), missed_gaps=missed,
        guardrail_relabels=len(result.guardrail_notes),
        prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
        cost_usd=usage.cost_usd)


def run_eval(inputs_dir: Path = DEFAULT_INPUTS, gold_path: Path = DEFAULT_GOLD,
             out_dir: Path = DEFAULT_OUT) -> dict:
    gold_all = json.loads(gold_path.read_text(encoding="utf-8"))
    dict_path = inputs_dir / "event_dictionary.csv"
    dictionary = load_event_dictionary(dict_path) if dict_path.exists() else []
    model = "mock" if is_offline() else get_client().model
    rows = []
    for path in sorted(inputs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        gold = gold_all.get(path.stem, [])
        full = run_pipeline(text, dictionary=dictionary, source_file=path.name)
        base = run_pipeline(text, dictionary=dictionary, source_file=path.name, single_pass=True)
        rows.append({"example": path.stem, "draft_score": full.draft_score.total,
                     "full": asdict(_variant(full, gold)),
                     "single_pass": asdict(_variant(base, gold))})
    report = {"mode": "offline-demo" if is_offline() else "llm", "model": model, "rows": rows}
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "mock" if is_offline() else model.replace("/", "_")
    (out_dir / f"{stem}_results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / f"{stem}_results.md").write_text(to_markdown(report), encoding="utf-8")
    return report


def to_markdown(report: dict) -> str:
    title = ("Offline demo (rule-based MockLLM, not a real model)" if report["mode"] ==
             "offline-demo" else f"Model: {report['model']}")
    lines = [f"# Evaluation: {title}", "",
             "| Example | Single-pass score | Full-pipeline score | Ambiguity recall (single / "
             "full) | Lint errors / warnings (full) | Open questions (full) | Guardrail relabels "
             "| Tokens (full) | Est. cost (full) |",
             "|---|---|---|---|---|---|---|---|---|"]
    offline = report["mode"] == "offline-demo"

    def tokens(v: dict) -> str:
        return "n/a (offline)" if offline else str(v["prompt_tokens"] + v["completion_tokens"])

    def cost(v: dict) -> str:
        return "n/a (offline)" if offline else f"${v['cost_usd']:.4f}"

    for r in report["rows"]:
        f, b = r["full"], r["single_pass"]
        lines.append(
            f"| {r['example']} | {b['score']:g} | {f['score']:g} | "
            f"{b['ambiguity_recall']:.0%} / {f['ambiguity_recall']:.0%} | "
            f"{f['lint_errors']} / {f['lint_warnings']} | {f['open_questions']} | "
            f"{f['guardrail_relabels']} | {tokens(f)} | {cost(f)} |")
    lines += ["", "Gaps missed by the full pipeline:", ""]
    for r in report["rows"]:
        missed = r["full"]["missed_gaps"]
        lines.append(f"- **{r['example']}**: {'; '.join(missed) if missed else 'none'}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if is_offline():
        print(f"*** {OFFLINE_BANNER} ***")
    report = run_eval(args.inputs, args.gold, args.out)
    print(to_markdown(report))


if __name__ == "__main__":
    main()
