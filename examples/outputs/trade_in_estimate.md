# Technical Spec: Trade-in estimate in phone checkout

> **Offline demo output.** Running in offline demo mode (no LLM key) — outputs are rule-based. Requirements are restated from the request; everything labelled *assumption* and every open question needs human review.

| Field | Value |
|---|---|
| Status | Draft, generated 2026-10-21 07:39 UTC |
| Mode | offline-demo (model: mock) |
| Pipeline | extract → draft → critique → revise |
| Source | examples/inputs/trade_in_estimate.md |
| Quality score | 99.5 / 100 |
| Open questions | 8 (1 blocking) |

## 1. Overview

Trade-in estimate in phone checkout for Nimbus Wireless customers on app or web. Headline ask: Customers should be able to enter their current device model and condition during phone checkout and see an estimated trade-in value. This spec captures 6 functional and 3 non-functional requirements, 6 tracking events, the rollout and test plan, and the open questions the request leaves unanswered (section 15).

## 2. Problem statement

Customers who upgrade their phone often abandon checkout at the trade-in step because they don't know what their current device is worth until after they ship it. Trade-in value is one of the top questions in upgrade calls to care. We want to give customers an instant estimate before they commit.

## 3. Goals

- Increase checkout completion for upgrade orders
- Reduce trade-in related calls to care

## 4. Non-goals

- Changing the device inspection process
- Trade-in for tablets and wearables (phones only for now)

## 5. User stories

**US-1** (should): As a Nimbus Wireless customer, I want to enter my current device model and condition during phone checkout and see an estimated trade-in value, so that it supports the goal: increase checkout completion for upgrade orders.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they enter their current device model and condition during phone checkout **then** an estimated trade-in value is displayed
- **Given** analytics is enabled for the session **when** they enter their current device model and condition during phone checkout **then** `trade_in_estimate_started` fires exactly once with all required properties

**US-2** (must): As a Nimbus Wireless customer, I want the estimate to be applied as a credit preview in the order summary, so that it supports the goal: increase checkout completion for upgrade orders.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they use the trade-in estimate **then** the estimate is applied as a credit preview in the order summary
- **Given** analytics is enabled for the session **when** they use the trade-in estimate **then** `trade_in_estimate_completed` fires exactly once with all required properties

**US-3** (must): As a Nimbus Wireless customer, I want to skip the trade-in step and continue checkout, so that it supports the goal: increase checkout completion for upgrade orders.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they skip the trade-in step and continue checkout **then** the customer can skip the trade-in step and continue checkout
- **Given** analytics is enabled for the session **when** they skip the trade-in step and continue checkout **then** `trade_in_estimate_skipped` fires exactly once with all required properties

**US-4** (must): As a Nimbus Wireless customer, I want the estimate to come from the existing Trade-In Pricing Service, so that it supports the goal: increase checkout completion for upgrade orders.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they use the trade-in estimate **then** the estimate comes from the existing Trade-In Pricing Service

**US-5** (should): As a Nimbus Wireless customer, I want to see a disclaimer that the final value is confirmed after device inspection, so that it supports the goal: increase checkout completion for upgrade orders.

- **Given** a signed-in Nimbus Wireless customer on app or web **when** they use the trade-in estimate **then** the page shows a disclaimer that the final value is confirmed after device inspection

## 6. Requirements

### 6.1 Functional

| ID | Requirement | Priority | Source | Refs |
|---|---|---|---|---|
| FR-1 | Customers should be able to enter their current device model and condition during phone checkout and see an estimated trade-in value. | should | input | F-4 |
| FR-2 | The estimate must be applied as a credit preview in the order summary. | must | input | F-5 |
| FR-3 | Customers must be able to skip the trade-in step and continue checkout. | must | input | F-6 |
| FR-4 | The estimate must come from the existing Trade-In Pricing Service. | must | input | F-7 |
| FR-5 | Show a disclaimer that the final value is confirmed after device inspection. | should | input | F-8 |
| FR-6 | Track the funnel from trade-in step viewed to estimate shown to order placed. | should | input | F-12 |

### 6.2 Non-functional

| ID | Category | Requirement | Priority | Source | Refs |
|---|---|---|---|---|---|
| NFR-1 | performance & usability | The estimate should load fast [measurable target for 'fast' TBD: OQ-3]. | should | input | F-9, OQ-3 |
| NFR-2 | accessibility | All new UI on app or web meets WCAG 2.1 AA (screen-reader labels, 4.5:1 contrast, full keyboard/switch access). | must | assumption | A-1 |
| NFR-3 | privacy | Tracking events contain zero PII: no names, phone numbers, free-text message content or full account/card numbers. | must | assumption | A-2 |
| NFR-4 | performance & usability | The flow should be easy to use [measurable target for 'easy' TBD: OQ-3]. | should | input | F-9, OQ-3 |

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
| `trade_in_estimate_viewed` | new | Fires once per page load when the trade-in estimate is at least 50% in the viewport | app, web |  |
| `trade_in_estimate_started` | new | Customer taps the trade-in estimate entry control and the trade-in estimate renders | app, web | FR-1 |
| `trade_in_estimate_completed` | new | The trade-in estimate result is rendered to the customer (client-side) | app, web | FR-2, FR-4, FR-5 |
| `trade_in_estimate_skipped` | new | Customer taps the skip control on the trade-in estimate step | app, web | FR-3 |
| `trade_in_estimate_failed` | new | Client receives an error or a timeout from the backing service | app, web |  |
| `order_placed` | existing | Existing trigger (see event dictionary, owner Device Commerce) | app, web |  |

### 7.3 Event properties

**`trade_in_estimate_viewed`** (new): The trade-in estimate is displayed to the customer

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `entry_point` | string | yes | Screen or link the customer came from |  |
| `screen_name` | string | yes | App screen or web page |  |

**`trade_in_estimate_started`** (new): Customer started the trade-in estimate

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `entry_point` | string | yes | Screen or link the customer came from |  |

**`trade_in_estimate_completed`** (new): The trade-in estimate returned a result

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `device_model` | string | yes | Device model the customer entered |  |
| `device_condition` | string | yes | Condition grade selected (values per OQ / service) |  |
| `estimate_amount` | number | yes | Estimated value shown, in USD |  |

**`trade_in_estimate_skipped`** (new): Customer skipped the trade-in estimate step

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `step_name` | string | yes | Name of the skipped step |  |

**`trade_in_estimate_failed`** (new): The trade-in estimate could not load or return a result

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `error_code` | string | yes | Service or client error code |  |
| `failure_stage` | string | yes | Step where the failure happened |  |

**`order_placed`** (existing): Order successfully submitted

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `order_id` | string | yes | As defined in the event dictionary |  |
| `order_type` | string | yes | As defined in the event dictionary |  |
| `order_value` | number | yes | As defined in the event dictionary |  |

### 7.4 Success metrics

| Metric | Definition | Target | Events |
|---|---|---|---|
| Increase checkout completion for upgrade orders | Sessions with `order_placed` ÷ sessions with `trade_in_estimate_viewed`, split by platform | TBD (OQ-4) | `trade_in_estimate_viewed`, `order_placed` |
| Reduce trade-in related calls to care | Care contacts on this topic per 1,000 customers who fired `trade_in_estimate_viewed` (care data source TBD, OQ-6). | TBD (OQ-5) | `trade_in_estimate_viewed` |

## 8. Data model & API changes

| Entity | Change | Fields | Description | Source |
|---|---|---|---|---|
| Event dictionary | add | `trade_in_estimate_completed`, `trade_in_estimate_failed`, `trade_in_estimate_skipped`, `trade_in_estimate_started`, `trade_in_estimate_viewed` | Register the new tracking events; update the modified ones: none. | assumption |

| Method | Path | Change | Description | Source |
|---|---|---|---|---|
| GET | `/v1/trade-in-pricing` | add | PROPOSED client-facing read endpoint backed by Trade-In Pricing Service (A-3); confirm contract, auth and caching. | assumption |

## 9. Dependencies

| Dependency | Type | Description | Source |
|---|---|---|---|
| Trade-In Pricing Service | service | The estimate must come from the existing Trade-In Pricing Service | input |
| Analytics / event dictionary owners | team | Review new and modified events before release. | assumption |

## 10. Edge cases

| ID | Scenario | Expected behaviour | Source |
|---|---|---|---|
| EC-1 | Trade-In Pricing Service times out or returns an error | Show a non-blocking error state, let the customer continue, and fire `trade_in_estimate_failed` with error_code. | assumption |
| EC-2 | Customer skips the step, then navigates back to it | The step is shown again with nothing pre-applied; no duplicate credit is created. | assumption |
| EC-3 | Customer in a group whose eligibility is unresolved (OQ-1: Are Nimbus Prepaid customers eligible?) | Behaviour follows the answer to OQ-1; until it is resolved the feature stays hidden for that group. | assumption |
| EC-4 | Customer starts on app and finishes on web (or vice versa) | Same content on both; events keep identical names and differ only in `platform`. | assumption |
| EC-5 | Analytics is blocked or consent is declined | The feature works normally; no events are sent and no errors are shown. | assumption |

## 11. Rollout & experiment plan

Feature flag: `trade_in_estimate_enabled` (source: assumption).

| Phase | Audience | Exposure | Exit criteria |
|---|---|---|---|
| Internal dogfood | Employee and test accounts | 0% | No P1/P2 defects; all events validated in the analytics debugger |
| Pilot | Nimbus Wireless customers on app or web | 5% | Error rate and care contacts at or below baseline for 7 days |
| Ramp | Same | 50% | Primary metric not worse than control |
| General availability | All eligible customers | 100% | Experiment readout signed off |

- **Hypothesis:** Exposing the trade-in estimate in phone checkout improves: Increase checkout completion for upgrade orders.
- **Variants:** control: current experience; treatment: trade-in estimate in phone checkout
- **Randomisation unit:** customer account (all lines on an account see the same variant)
- **Primary metric:** Increase checkout completion for upgrade orders
- **Guardrails:** `trade_in_estimate_failed` rate, care contact rate
- **Minimum detectable effect:** TBD (OQ-7)

Rollback: Turn off `trade_in_estimate_enabled`; customers fall back to the current experience. Basis: A-4.

## 12. Test plan

| ID | Type | Title | Covers | Events verified | Expected |
|---|---|---|---|---|---|
| TC-1 | e2e | Verify FR-1 | FR-1, US-1 |  | An estimated trade-in value is displayed |
| TC-2 | e2e | Verify FR-2 | FR-2, US-2 |  | The estimate is applied as a credit preview in the order summary |
| TC-3 | e2e | Verify FR-3 | FR-3, US-3 |  | The customer can skip the trade-in step and continue checkout |
| TC-4 | e2e | Verify FR-4 | FR-4, US-4 |  | The estimate comes from the existing Trade-In Pricing Service |
| TC-5 | e2e | Verify FR-5 | FR-5, US-5 |  | The page shows a disclaimer that the final value is confirmed after device inspection |
| TC-6 | analytics | Verify FR-6 | FR-6 |  | Track the funnel from trade-in step viewed to estimate shown to order placed |
| TC-7 | performance | Verify NFR-1 | NFR-1 |  | The estimate loads fast |
| TC-8 | accessibility | Verify NFR-2 | NFR-2 |  | All new UI on app or web meets WCAG 2.1 AA (screen-reader labels, 4.5:1 contrast, full keyboard/switch access) |
| TC-9 | analytics | Verify NFR-3 | NFR-3 |  | Tracking events contain zero PII: no names, phone numbers, free-text message content or full account/card numbers |
| TC-10 | analytics | Analytics: `trade_in_estimate_viewed` payload |  | `trade_in_estimate_viewed` | Fires exactly once with global properties and: entry_point, screen_name; values match the UI. |
| TC-11 | analytics | Analytics: `trade_in_estimate_started` payload | FR-1 | `trade_in_estimate_started` | Fires exactly once with global properties and: entry_point; values match the UI. |
| TC-12 | analytics | Analytics: `trade_in_estimate_completed` payload | FR-2, FR-4, FR-5 | `trade_in_estimate_completed` | Fires exactly once with global properties and: device_model, device_condition, estimate_amount; values match the UI. |
| TC-13 | analytics | Analytics: `trade_in_estimate_skipped` payload | FR-3 | `trade_in_estimate_skipped` | Fires exactly once with global properties and: step_name; values match the UI. |
| TC-14 | analytics | Analytics: `trade_in_estimate_failed` payload |  | `trade_in_estimate_failed` | Fires exactly once with global properties and: error_code, failure_stage; values match the UI. |
| TC-15 | analytics | Analytics: `order_placed` payload |  | `order_placed` | Fires exactly once with global properties and: order_id, order_type, order_value; values match the UI. |
| TC-16 | performance | Verify NFR-4 | NFR-4 |  | The flow is easy to use [measurable target for 'easy' TBD: OQ-3] |

## 13. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Event names drift between app and web, breaking the cross-platform funnel | medium | high | Treat section 7 as the single source; lint against the event dictionary in CI. |
| Trade-In Pricing Service latency or outage degrades the experience | medium | medium | Timeouts with graceful fallback; alert on the failed-event rate. |
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
| OQ-1 | Are Nimbus Prepaid customers eligible? | The request explicitly leaves this open; it changes scope or eligibility logic. | Product | yes |
| OQ-2 | Should we A/B test the placement of the trade-in step? | The request explicitly leaves this open; it changes scope or eligibility logic. | Analytics | no |
| OQ-3 | What measurable target defines 'fast', 'easy' in: "The estimate should load fast and the flow should be easy to use"? | Without a threshold the requirement cannot be tested or accepted. | Analytics | no |
| OQ-4 | What is the target and timeframe for: "Increase checkout completion for upgrade orders"? | Success metrics need a target to size the rollout and judge the launch. | Analytics | no |
| OQ-5 | What is the target and timeframe for: "Reduce trade-in related calls to care"? | Success metrics need a target to size the rollout and judge the launch. | Analytics | no |
| OQ-6 | Which care-contact data source and reason codes identify the calls in: "Reduce trade-in related calls to care"? | The metric cannot be computed from app/web events alone. | Analytics | no |
| OQ-7 | What are the primary metric, minimum detectable effect and planned duration of the experiment? | Needed to size the test and decide when to stop it. | Analytics | no |
| OQ-8 | Is `trade_in_estimate_viewed` the same user action as existing `trade_in_quote_viewed`? If so, reuse the existing event. | Avoids two events for one action, which double-counts the funnel. | Analytics | no |

## Appendix A. Quality score

Deterministic rubric score: **99.5 / 100**.

| Category | Score | Max |
|---|---|---|
| Section completeness | 20 | 20 |
| User stories & acceptance criteria | 15 | 15 |
| Requirement quality | 20 | 20 |
| Tracking plan | 19.5 | 20 |
| Consistency & traceability | 15 | 15 |
| Ambiguity handling | 10 | 10 |

- **info** (NFR-1): Vague wording (fast) is deferred to an open question; resolve before build.
- **info** (NFR-4): Vague wording (easy) is deferred to an open question; resolve before build.
- **warning** (trade_in_estimate_viewed): [dictionary:synonym-drift] 'trade_in_estimate_viewed' matches existing event 'trade_in_quote_viewed' once synonyms are normalised (e.g. estimate/quote, tap/click).

## Appendix B. Event dictionary lint

Checked 6 events against 11 dictionary entries.

| Severity | Event | Rule | Finding | Suggestion |
|---|---|---|---|---|
| warning | `trade_in_estimate_viewed` | synonym-drift | 'trade_in_estimate_viewed' matches existing event 'trade_in_quote_viewed' once synonyms are normalised (e.g. estimate/quote, tap/click). | Confirm whether 'trade_in_quote_viewed' already measures this action; reuse it if so. |
