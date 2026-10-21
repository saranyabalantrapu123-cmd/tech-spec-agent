# Technical Spec: Unified plan comparison page across app and web

> **Offline demo output.** Running in offline demo mode (no LLM key) — outputs are rule-based. Requirements are restated from the request; everything labelled *assumption* and every open question needs human review.

| Field | Value |
|---|---|
| Status | Draft, generated 2026-10-21 07:39 UTC |
| Mode | offline-demo (model: mock) |
| Pipeline | extract → draft → critique → revise |
| Source | examples/inputs/plan_comparison.md |
| Quality score | 98.5 / 100 |
| Open questions | 7 (1 blocking) |

## 1. Overview

Unified plan comparison page across app and web for Nimbus Wireless customers on app or web. Headline ask: A single plan comparison page with the same layout and plan attributes on app and web. This spec captures 7 functional and 3 non-functional requirements, 4 tracking events, the rollout and test plan, and the open questions the request leaves unanswered (section 15).

## 2. Problem statement

Today the app shows plans as a carousel of cards while the website has a comparison table, and the two show different plan attributes. Customers who start on one surface and finish on the other get confused. Analytics cannot compare the two funnels because the events are named differently on each platform. We'd like to run this as an experiment against the current pages.

## 3. Goals

- Increase plan change conversion from the comparison page
- Get one funnel for app and web

## 4. Non-goals

- Changing plan prices or creating new plans
- Prepaid plans (Nimbus Prepaid will follow later)

## 5. User stories

**US-1** (should): As a Nimbus Wireless customer, I want a single plan comparison page with the same layout and plan attributes on app and web, so that it supports the goal: increase plan change conversion from the comparison page.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they use the plan comparison **then** there is a single plan comparison page with the same layout and plan attributes on app and web
- **Given** analytics is enabled for the session **when** they use the plan comparison **then** `plan_comparison_viewed` fires exactly once with all required properties

**US-2** (must): As a Nimbus Wireless customer, I want to select up to 3 plans to compare side by side, so that it supports the goal: increase plan change conversion from the comparison page.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they select up to 3 plans to compare side by side **then** the customer can select up to 3 plans to compare side by side
- **Given** analytics is enabled for the session **when** they select up to 3 plans to compare side by side **then** `plan_comparison_plan_selected` fires exactly once with all required properties

**US-3** (should): As a Nimbus Wireless customer, I want to see monthly price, data allowance, hotspot allowance and included perks for each plan, so that it supports the goal: increase plan change conversion from the comparison page.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they use the plan comparison **then** the page shows monthly price, data allowance, hotspot allowance and included perks for each plan

**US-4** (must): As a Nimbus Wireless customer, I want to filter plans by number of lines, so that it supports the goal: increase plan change conversion from the comparison page.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they filter plans by number of lines **then** the customer can filter plans by number of lines
- **Given** analytics is enabled for the session **when** they filter plans by number of lines **then** `plan_comparison_filter_applied` fires exactly once with all required properties

**US-5** (must): As a Nimbus Wireless customer, I want selecting a plan to take me to the existing plan change checkout, so that it supports the goal: increase plan change conversion from the comparison page.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they use the plan comparison **then** selecting a plan takes the customer to the existing plan change checkout

**US-6** (must): As a Nimbus Wireless customer, I want plan content to come from the Plan Catalog API so app and web never disagree, so that it supports the goal: increase plan change conversion from the comparison page.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they use the plan comparison **then** plan content comes from the Plan Catalog API so app and web never disagree

## 6. Requirements

### 6.1 Functional

| ID | Requirement | Priority | Source | Refs |
|---|---|---|---|---|
| FR-1 | A single plan comparison page with the same layout and plan attributes on app and web. | should | input | F-4 |
| FR-2 | Customers must be able to select up to 3 plans to compare side by side. | must | input | F-5 |
| FR-3 | Show monthly price, data allowance, hotspot allowance and included perks for each plan. | should | input | F-6 |
| FR-4 | Customers must be able to filter plans by number of lines. | must | input | F-7 |
| FR-5 | Selecting a plan must take the customer to the existing plan change checkout. | must | input | F-8 |
| FR-6 | Plan content must come from the Plan Catalog API so app and web never disagree. | must | input | F-9 |
| FR-7 | Use the same event names on both platforms. | should | input | F-13 |

### 6.2 Non-functional

| ID | Category | Requirement | Priority | Source | Refs |
|---|---|---|---|---|---|
| NFR-1 | performance & usability | The page should be fast and look modern, with better accessibility [measurable target for 'fast', 'modern', 'better' TBD: OQ-2]. | should | input | F-10, OQ-2 |
| NFR-2 | accessibility | All new UI on app or web meets WCAG 2.1 AA (screen-reader labels, 4.5:1 contrast, full keyboard/switch access). | must | assumption | A-1 |
| NFR-3 | privacy | Tracking events contain zero PII: no names, phone numbers, free-text message content or full account/card numbers. | must | assumption | A-2 |

## 7. Analytics & tracking plan

Naming convention: snake_case <object>_<action>; action is a past-tense verb (viewed, selected, submitted…).

### 7.1 Global properties (sent with every event)

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `platform` | enum | yes | Surface the event fired on (app or web) | app, web |
| `brand` | enum | yes | Brand the customer account belongs to | nimbus_wireless, nimbus_prepaid |
| `session_id` | string | yes | Analytics session identifier |  |

### 7.2 Events

| Event | Status | Trigger | Platforms | Requirements |
|---|---|---|---|---|
| `plan_comparison_viewed` | modified | Fires once per page load when the plan comparison is at least 50% in the viewport | app, web | FR-1, FR-3 |
| `plan_comparison_plan_selected` | new | Customer taps the select control on an item card | app, web | FR-2, FR-5 |
| `plan_comparison_filter_applied` | new | Filter value changes and results re-render | app, web | FR-4 |
| `plan_comparison_failed` | new | Client receives an error or a timeout from the backing service | app, web | FR-6 |

### 7.3 Event properties

**`plan_comparison_viewed`** (modified): The plan comparison is displayed to the customer

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `entry_point` | string | yes | Screen or link the customer came from |  |
| `screen_name` | string | yes | App screen or web page |  |

**`plan_comparison_plan_selected`** (new): Customer selected an item to compare or buy

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `plan_id` | string | yes | Catalog ID of the plan |  |
| `monthly_price` | number | yes | Monthly price shown, in USD |  |
| `position` | integer | yes | 1-based position of the item on the page |  |

**`plan_comparison_filter_applied`** (new): Customer applied a filter

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `filter_name` | string | yes | Filter used |  |
| `filter_value` | string | yes | Value chosen |  |

**`plan_comparison_failed`** (new): The plan comparison could not load or return a result

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `error_code` | string | yes | Service or client error code |  |
| `failure_stage` | string | yes | Step where the failure happened |  |

### 7.4 Success metrics

| Metric | Definition | Target | Events |
|---|---|---|---|
| Increase plan change conversion from the comparison page | Sessions with `plan_comparison_plan_selected` ÷ sessions with `plan_comparison_viewed`, split by platform | TBD (OQ-3) | `plan_comparison_viewed`, `plan_comparison_plan_selected` |
| Get one funnel for app and web | Share of `plan_comparison_viewed` → `plan_comparison_plan_selected` funnel volume reported from identical event names on app and web (split by `platform`); 100% when no platform-specific events remain | TBD (OQ-4) | `plan_comparison_viewed`, `plan_comparison_plan_selected` |

## 8. Data model & API changes

| Entity | Change | Fields | Description | Source |
|---|---|---|---|---|
| Event dictionary | add | `plan_comparison_failed`, `plan_comparison_filter_applied`, `plan_comparison_plan_selected` | Register the new tracking events; update the modified ones: plan_comparison_viewed. | assumption |

| Method | Path | Change | Description | Source |
|---|---|---|---|---|
| GET | `/v1/plan-catalog` | add | PROPOSED client-facing read endpoint backed by Plan Catalog API (A-3); confirm contract, auth and caching. | assumption |

## 9. Dependencies

| Dependency | Type | Description | Source |
|---|---|---|---|
| Plan Catalog API | service | Plan content must come from the Plan Catalog API so app and web never disagree | input |
| Analytics / event dictionary owners | team | Review new and modified events before release. | assumption |

## 10. Edge cases

| ID | Scenario | Expected behaviour | Source |
|---|---|---|---|
| EC-1 | Plan Catalog API times out or returns an error | Show a non-blocking error state, let the customer continue, and fire `plan_comparison_failed` with error_code. | assumption |
| EC-2 | Customer tries to select more than 3 items | Selection beyond 3 is blocked with an inline message. | assumption |
| EC-3 | A filter combination returns no results | Show an empty state with a reset action. | assumption |
| EC-4 | Customer in a group whose eligibility is unresolved (OQ-1: Can logged-out visitors see the page?) | Behaviour follows the answer to OQ-1; until it is resolved the feature stays hidden for that group. | assumption |
| EC-5 | Customer starts on app and finishes on web (or vice versa) | Same content on both; events keep identical names and differ only in `platform`. | assumption |
| EC-6 | Analytics is blocked or consent is declined | The feature works normally; no events are sent and no errors are shown. | assumption |

## 11. Rollout & experiment plan

Feature flag: `plan_comparison_enabled` (source: assumption).

| Phase | Audience | Exposure | Exit criteria |
|---|---|---|---|
| Internal dogfood | Employee and test accounts | 0% | No P1/P2 defects; all events validated in the analytics debugger |
| Pilot | Nimbus Wireless customers on app or web | 5% | Error rate and care contacts at or below baseline for 7 days |
| Ramp | Same | 50% | Primary metric not worse than control |
| General availability | All eligible customers | 100% | Experiment readout signed off |

- **Hypothesis:** Exposing the unified plan comparison page across app and web improves: Increase plan change conversion from the comparison page.
- **Variants:** control: current experience; treatment: unified plan comparison page across app and web
- **Randomisation unit:** customer account (all lines on an account see the same variant)
- **Primary metric:** Increase plan change conversion from the comparison page
- **Guardrails:** `plan_comparison_failed` rate, care contact rate
- **Minimum detectable effect:** TBD (OQ-5)

Rollback: Turn off `plan_comparison_enabled`; customers fall back to the current experience. Basis: A-4.

## 12. Test plan

| ID | Type | Title | Covers | Events verified | Expected |
|---|---|---|---|---|---|
| TC-1 | e2e | Verify FR-1 | FR-1, US-1 |  | There is a single plan comparison page with the same layout and plan attributes on app and web |
| TC-2 | e2e | Verify FR-2 | FR-2, US-2 |  | The customer can select up to 3 plans to compare side by side |
| TC-3 | e2e | Verify FR-3 | FR-3, US-3 |  | The page shows monthly price, data allowance, hotspot allowance and included perks for each plan |
| TC-4 | e2e | Verify FR-4 | FR-4, US-4 |  | The customer can filter plans by number of lines |
| TC-5 | e2e | Verify FR-5 | FR-5, US-5 |  | Selecting a plan takes the customer to the existing plan change checkout |
| TC-6 | e2e | Verify FR-6 | FR-6, US-6 |  | Plan content comes from the Plan Catalog API so app and web never disagree |
| TC-7 | analytics | Verify FR-7 | FR-7 |  | Use the same event names on both platforms |
| TC-8 | performance | Verify NFR-1 | NFR-1 |  | The page is fast and look modern, with better accessibility |
| TC-9 | accessibility | Verify NFR-2 | NFR-2 |  | All new UI on app or web meets WCAG 2.1 AA (screen-reader labels, 4.5:1 contrast, full keyboard/switch access) |
| TC-10 | analytics | Verify NFR-3 | NFR-3 |  | Tracking events contain zero PII: no names, phone numbers, free-text message content or full account/card numbers |
| TC-11 | analytics | Analytics: `plan_comparison_viewed` payload | FR-1, FR-3 | `plan_comparison_viewed` | Fires exactly once with global properties and: entry_point, screen_name; values match the UI. |
| TC-12 | analytics | Analytics: `plan_comparison_plan_selected` payload | FR-2, FR-5 | `plan_comparison_plan_selected` | Fires exactly once with global properties and: plan_id, monthly_price, position; values match the UI. |
| TC-13 | analytics | Analytics: `plan_comparison_filter_applied` payload | FR-4 | `plan_comparison_filter_applied` | Fires exactly once with global properties and: filter_name, filter_value; values match the UI. |
| TC-14 | analytics | Analytics: `plan_comparison_failed` payload | FR-6 | `plan_comparison_failed` | Fires exactly once with global properties and: error_code, failure_stage; values match the UI. |

## 13. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Event names drift between app and web, breaking the cross-platform funnel | medium | high | Treat section 7 as the single source; lint against the event dictionary in CI. |
| Plan Catalog API latency or outage degrades the experience | medium | medium | Timeouts with graceful fallback; alert on the failed-event rate. |
| 1 blocking open question(s) delay build start | high | medium | Review open questions with owners before sprint planning. |
| Experiment is under-powered for the expected effect | medium | medium | Size the test once the MDE is agreed. |

## 14. Assumptions

| ID | Assumption | Validate with |
|---|---|---|
| A-1 | Accessibility follows the company default of WCAG 2.1 AA. | UX Design |
| A-2 | Analytics events must not carry PII; this is standard instrumentation policy. | Privacy / Analytics governance |
| A-3 | API contracts below are placeholders until the owning team confirms them. | Owning engineering teams |
| A-4 | Rollout stages follow the standard flag-based ramp. | Release management |

## 15. Open questions

| ID | Question | Why it matters | Owner | Blocking |
|---|---|---|---|---|
| OQ-1 | Can logged-out visitors see the page? | The request explicitly leaves this open; it changes scope or eligibility logic. | Product | yes |
| OQ-2 | What measurable target defines 'fast', 'modern', 'better' in: "The page should be fast and look modern, with better accessibility"? | Without a threshold the requirement cannot be tested or accepted. | Analytics | no |
| OQ-3 | What is the target and timeframe for: "Increase plan change conversion from the comparison page"? | Success metrics need a target to size the rollout and judge the launch. | Analytics | no |
| OQ-4 | What is the target and timeframe for: "Get one funnel for app and web"? | Success metrics need a target to size the rollout and judge the launch. | Analytics | no |
| OQ-5 | What are the primary metric, minimum detectable effect and planned duration of the experiment? | Needed to size the test and decide when to stop it. | Analytics | no |
| OQ-6 | Is `plan_comparison_plan_selected` the same user action as existing `PlanCompare_Select`? If so, reuse the existing event. | Avoids two events for one action, which double-counts the funnel. | Analytics | no |
| OQ-7 | Property 'monthly_price' is 'number' here but 'string' in the dictionary (on 'PlanCompare_Select'). Align the type or version the property? | Conflicting types break joins and dashboards across events. | Analytics | no |

## Appendix A. Quality score

Deterministic rubric score: **98.5 / 100**.

| Category | Score | Max |
|---|---|---|
| Section completeness | 20 | 20 |
| User stories & acceptance criteria | 15 | 15 |
| Requirement quality | 20 | 20 |
| Tracking plan | 18.5 | 20 |
| Consistency & traceability | 15 | 15 |
| Ambiguity handling | 10 | 10 |

- **info** (NFR-1): Vague wording (fast, modern, better) is deferred to an open question; resolve before build.
- **warning** (plan_comparison_plan_selected): [dictionary:possible-duplicate] 'plan_comparison_plan_selected' is very similar to existing event 'PlanCompare_Select'.
- **error** (plan_comparison_plan_selected): [dictionary:property-type-conflict] Property 'monthly_price' is 'number' here but 'string' in the dictionary (on 'PlanCompare_Select').

## Appendix B. Event dictionary lint

Checked 4 events against 11 dictionary entries.

| Severity | Event | Rule | Finding | Suggestion |
|---|---|---|---|---|
| warning | `plan_comparison_plan_selected` | possible-duplicate | 'plan_comparison_plan_selected' is very similar to existing event 'PlanCompare_Select'. | Confirm with the dictionary owner whether this is the same user action. |
| error | `plan_comparison_plan_selected` | property-type-conflict | Property 'monthly_price' is 'number' here but 'string' in the dictionary (on 'PlanCompare_Select'). | Align the type with the dictionary, or version the property. |
