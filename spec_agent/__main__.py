"""Command line interface.

    python -m spec_agent generate examples/inputs/trade_in_estimate.md --format md,docx,json
    python -m spec_agent score examples/outputs/trade_in_estimate.json
    python -m spec_agent lint examples/outputs/trade_in_estimate.json \
        --event-dictionary examples/inputs/event_dictionary.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .linter import LintReport, lint_events, load_event_dictionary
from .llm import OFFLINE_BANNER, is_offline
from .pipeline import read_context_files, run_pipeline
from .renderers import write_outputs
from .schema import ScoreReport, TechSpec
from .scorer import score_spec


def _print_score(score: ScoreReport, verbose: bool = True) -> None:
    print(f"Quality score: {score.total:g} / {score.max_total:g}")
    for c in score.categories:
        print(f"  {c.name:<36} {c.score:>5g} / {c.max_score:g}")
        if verbose:
            for f in c.findings:
                if f.severity != "info":
                    print(f"      - [{f.severity}] {f.location}: {f.message}")


def _print_lint(lint: LintReport) -> None:
    print(f"Event dictionary lint: {len(lint.errors)} error(s), {len(lint.warnings)} warning(s) "
          f"({lint.checked_events} events vs {lint.dictionary_size} dictionary entries)")
    for f in lint.findings:
        print(f"  - [{f.severity}] {f.event} ({f.rule}): {f.message}")


def cmd_generate(args: argparse.Namespace) -> int:
    if is_offline():
        print(f"*** {OFFLINE_BANNER} ***")
    request_path = Path(args.input)
    dictionary = load_event_dictionary(args.event_dictionary) if args.event_dictionary else []
    result = run_pipeline(
        request_path.read_text(encoding="utf-8"),
        context_docs=read_context_files(args.context or []), dictionary=dictionary,
        source_file=request_path.as_posix(), single_pass=args.single_pass)
    formats = [f.strip() for f in args.format.split(",") if f.strip()]
    stem = args.name or request_path.stem
    paths = write_outputs(result.spec, args.out_dir, stem, formats, result.score, result.lint,
                          result.guardrail_notes)
    print(f"Spec: {result.spec.title}")
    if result.critique is not None:
        print(f"Draft score {result.draft_score.total:g} -> revised score {result.score.total:g} "
              f"({len(result.critique.issues)} critique issues addressed)")
    _print_score(result.score, verbose=args.verbose)
    if result.lint:
        print(f"Event dictionary lint: {len(result.lint.errors)} error(s), "
              f"{len(result.lint.warnings)} warning(s)")
    for note in result.guardrail_notes:
        print(f"Guardrail: {note}")
    if not result.offline:
        print(f"LLM usage: {result.client.usage.summary()}")
    for p in paths:
        print(f"Wrote {p}")
    return 0


def _load_spec(path: str) -> TechSpec:
    return TechSpec.model_validate_json(Path(path).read_text(encoding="utf-8"))


def cmd_score(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec)
    lint = (lint_events(spec, load_event_dictionary(args.event_dictionary))
            if args.event_dictionary else None)
    score = score_spec(spec, lint)
    _print_score(score)
    if args.min_score is not None and score.total < args.min_score:
        print(f"FAIL: score {score.total:g} < --min-score {args.min_score:g}")
        return 1
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    lint = lint_events(_load_spec(args.spec), load_event_dictionary(args.event_dictionary))
    _print_lint(lint)
    return 1 if lint.errors and args.strict else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spec_agent",
                                     description="Turn feature requests into technical specs.")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate a spec from a feature request file")
    g.add_argument("input", help="Feature request (.md or .txt)")
    g.add_argument("--format", default="md,docx,json", help="Comma list of md,docx,json")
    g.add_argument("--out-dir", default="examples/outputs")
    g.add_argument("--name", help="Output file stem (default: input file stem)")
    g.add_argument("--context", nargs="*", help="Extra context files (notes, prior specs)")
    g.add_argument("--event-dictionary", help="CSV of existing tracking events to lint against")
    g.add_argument("--single-pass", action="store_true",
                   help="Baseline: extract + draft only, no critique/revise")
    g.add_argument("-v", "--verbose", action="store_true", help="Print every score finding")
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("score", help="Score an existing spec JSON (deterministic, no LLM)")
    s.add_argument("spec")
    s.add_argument("--event-dictionary", help="Also lint events and deduct unresolved findings")
    s.add_argument("--min-score", type=float, help="Exit 1 if the score is below this (CI gate)")
    s.set_defaults(func=cmd_score)

    lt = sub.add_parser("lint", help="Lint a spec's tracking events against an event dictionary")
    lt.add_argument("spec")
    lt.add_argument("--event-dictionary", required=True)
    lt.add_argument("--strict", action="store_true", help="Exit 1 if there are lint errors")
    lt.set_defaults(func=cmd_lint)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
