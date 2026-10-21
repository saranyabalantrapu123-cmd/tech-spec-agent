# Evaluation: Offline demo (rule-based MockLLM, not a real model)

| Example | Single-pass score | Full-pipeline score | Ambiguity recall (single / full) | Lint errors / warnings (full) | Open questions (full) | Guardrail relabels | Tokens (full) | Est. cost (full) |
|---|---|---|---|---|---|---|---|---|
| ai_chat_bill_page | 96.8 | 99 | 75% / 88% | 0 / 2 | 8 | 0 | n/a (offline) | n/a (offline) |
| plan_comparison | 96 | 98.5 | 75% / 88% | 1 / 1 | 7 | 0 | n/a (offline) | n/a (offline) |
| trade_in_estimate | 97.3 | 99.5 | 75% / 75% | 0 / 1 | 8 | 0 | n/a (offline) | n/a (offline) |

Gaps missed by the full pipeline:

- **ai_chat_bill_page**: Live-agent availability (hours, queue) for escalation
- **plan_comparison**: Allowed values for the number-of-lines filter
- **trade_in_estimate**: Allowed device condition grades; What happens when the final inspected value differs from the estimate
