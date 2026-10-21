# Technical Spec: AI chat assistant entry point on the bill page

> **Offline demo output.** Running in offline demo mode (no LLM key) — outputs are rule-based. Requirements are restated from the request; everything labelled *assumption* and every open question needs human review.

| Field | Value |
|---|---|
| Status | Draft, generated 2026-10-21 07:39 UTC |
| Mode | offline-demo (model: mock) |
| Pipeline | extract → draft → critique → revise |
| Source | examples/inputs/ai_chat_bill_page.md |
| Quality score | 99 / 100 |
| Open questions | 8 (2 blocking) |

## 1. Overview

AI chat assistant entry point on the bill page for Nimbus Wireless or Nimbus Prepaid customers on app or web. Headline ask: Add a "Questions about your bill?" entry point on the bill page that opens the AI chat assistant. This spec captures 5 functional and 4 non-functional requirements, 5 tracking events, the rollout and test plan, and the open questions the request leaves unanswered (section 15).

## 2. Problem statement

Billing questions are the largest driver of care calls in the first week after a bill is issued. Most of them are simple, such as why the bill went up or when a promo credit ends. The AI chat assistant already exists in the Help section, but very few customers find it from the bill page.

## 3. Goals

- Reduce billing-related calls to care
- Increase the share of bill-page chat sessions resolved without an agent

## 4. Non-goals

- Changing the assistant's underlying model or knowledge base
- Proactive push notifications about the bill

## 5. User stories

**US-1** (should): As a Nimbus Wireless or Nimbus Prepaid customer, I want a "Questions about your bill?" entry point on the bill page that opens the AI chat assistant, so that it supports the goal: reduce billing-related calls to care.

- **Given** a signed-in Nimbus Wireless or Nimbus Prepaid customer on app or web **when** they use the AI chat assistant **then** there is a "Questions about your bill?" entry point on the bill page that opens the AI chat assistant
- **Given** analytics is enabled for the session **when** they use the AI chat assistant **then** `ai_chat_assistant_opened` fires exactly once with all required properties

**US-2** (must): As a Nimbus Wireless or Nimbus Prepaid customer, I want the assistant to receive the current bill period and account context so I do not have to re-explain when opened from the bill page, so that it supports the goal: reduce billing-related calls to care.

- **Given** a signed-in Nimbus Wireless or Nimbus Prepaid customer on app or web **when** they use the AI chat assistant **then** the assistant receives the current bill period and account context so the customer does not have to re-explain when opened from the bill page

**US-3** (must): As a Nimbus Wireless or Nimbus Prepaid customer, I want to escalate to a live care agent from the chat at any time, so that it supports the goal: reduce billing-related calls to care.

- **Given** a signed-in Nimbus Wireless or Nimbus Prepaid customer on app or web **when** they escalate to a live care agent from the chat at any time **then** the customer can escalate to a live care agent from the chat at any time
- **Given** analytics is enabled for the session **when** they escalate to a live care agent from the chat at any time **then** `ai_chat_assistant_escalated` fires exactly once with all required properties

**US-4** (should): As a Nimbus Wireless or Nimbus Prepaid customer, I want to rate each answer with thumbs up or thumbs down, so that it supports the goal: reduce billing-related calls to care.

- **Given** a signed-in Nimbus Wireless or Nimbus Prepaid customer on app or web **when** they rate each answer with thumbs up or thumbs down **then** the customer can rate each answer with thumbs up or thumbs down
- **Given** analytics is enabled for the session **when** they rate each answer with thumbs up or thumbs down **then** `ai_chat_assistant_feedback_submitted` fires exactly once with all required properties

## 6. Requirements

### 6.1 Functional

| ID | Requirement | Priority | Source | Refs |
|---|---|---|---|---|
| FR-1 | Add a "Questions about your bill?" entry point on the bill page that opens the AI chat assistant. | should | input | F-4 |
| FR-2 | When opened from the bill page, the assistant must receive the current bill period and account context so the customer does not have to re-explain. | must | input | F-5 |
| FR-3 | Customers must be able to escalate to a live care agent from the chat at any time. | must | input | F-7 |
| FR-4 | Customers should be able to rate each answer with thumbs up or thumbs down. | should | input | F-8 |
| FR-5 | Track entry point views, chat opens, messages, escalations and ratings. | should | input | F-12 |

### 6.2 Non-functional

| ID | Category | Requirement | Priority | Source | Refs |
|---|---|---|---|---|---|
| NFR-1 | privacy & security | The assistant must never display full payment card or bank account numbers. | must | input | F-6 |
| NFR-2 | performance & usability | The entry point should be intuitive [measurable target for 'intuitive' TBD: OQ-3]. | should | input | F-9, OQ-3 |
| NFR-3 | accessibility | All new UI on app or web meets WCAG 2.1 AA (screen-reader labels, 4.5:1 contrast, full keyboard/switch access). | must | assumption | A-1 |
| NFR-4 | privacy | Tracking events contain zero PII: no names, phone numbers, free-text message content or full account/card numbers. | must | assumption | A-2 |
| NFR-5 | performance & usability | The assistant should respond quickly [measurable target for 'quickly' TBD: OQ-3]. | should | input | F-9, OQ-3 |

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
| `ai_chat_assistant_entry_viewed` | new | Fires once per page load when the AI chat assistant entry point is at least 50% in the viewport | app, web |  |
| `ai_chat_assistant_opened` | new | Customer taps the AI chat assistant entry control and the AI chat assistant renders | app, web | FR-1, FR-2 |
| `ai_chat_assistant_message_sent` | new | Message is submitted from the AI chat assistant input (fires on client send) | app, web |  |
| `ai_chat_assistant_escalated` | new | Customer confirms the escalate-to-agent action and the handoff request is accepted | app, web | FR-3 |
| `ai_chat_assistant_feedback_submitted` | new | Customer taps thumbs up or thumbs down on an answer | app, web | FR-4 |

### 7.3 Event properties

**`ai_chat_assistant_entry_viewed`** (new): The AI chat assistant entry point is displayed to the customer

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `entry_point` | string | yes | Screen or link the customer came from |  |
| `screen_name` | string | yes | App screen or web page |  |

**`ai_chat_assistant_opened`** (new): Customer opened the AI chat assistant

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `entry_point` | string | yes | Screen or link the customer came from |  |

**`ai_chat_assistant_message_sent`** (new): Customer sent a message in the AI chat assistant

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `message_count` | integer | yes | Count of customer messages in the session so far |  |
| `message_length` | integer | yes | Characters in the message (content is never sent) |  |

**`ai_chat_assistant_escalated`** (new): Conversation escalated to a live agent

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `message_count` | integer | yes | Customer messages before escalation |  |
| `escalation_reason` | string | no | Reason selected by the customer, if any |  |

**`ai_chat_assistant_feedback_submitted`** (new): Customer rated an answer

| Property | Type | Required | Description | Allowed values |
|---|---|---|---|---|
| `rating` | enum | yes | Rating given | thumbs_up, thumbs_down |
| `answer_id` | string | yes | ID of the rated answer |  |

### 7.4 Success metrics

| Metric | Definition | Target | Events |
|---|---|---|---|
| Reduce billing-related calls to care | Care contacts on this topic per 1,000 customers who fired `ai_chat_assistant_entry_viewed` (care data source TBD, OQ-5). | TBD (OQ-4) | `ai_chat_assistant_entry_viewed` |
| Increase the share of bill-page chat sessions resolved without an agent | 1 - (sessions with `ai_chat_assistant_escalated` ÷ sessions with `ai_chat_assistant_opened`) | TBD (OQ-6) | `ai_chat_assistant_opened`, `ai_chat_assistant_escalated` |

## 8. Data model & API changes

| Entity | Change | Fields | Description | Source |
|---|---|---|---|---|
| Event dictionary | add | `ai_chat_assistant_entry_viewed`, `ai_chat_assistant_escalated`, `ai_chat_assistant_feedback_submitted`, `ai_chat_assistant_message_sent`, `ai_chat_assistant_opened` | Register the new tracking events; update the modified ones: none. | assumption |

## 9. Dependencies

| Dependency | Type | Description | Source |
|---|---|---|---|
| Legal | legal | Legal needs to review how bill data is shared with the assistant | input |
| Analytics / event dictionary owners | team | Review new and modified events before release. | assumption |

## 10. Edge cases

| ID | Scenario | Expected behaviour | Source |
|---|---|---|---|
| EC-1 | Customer types a full card or bank number into the chat | The number is masked in the transcript and never sent to analytics. | assumption |
| EC-2 | Customer in a group whose eligibility is unresolved (OQ-2: Should account sub-users (non-owners) see the entry point?) | Behaviour follows the answer to OQ-2; until it is resolved the feature stays hidden for that group. | assumption |
| EC-3 | Customer starts on app and finishes on web (or vice versa) | Same content on both; events keep identical names and differ only in `platform`. | assumption |
| EC-4 | Analytics is blocked or consent is declined | The feature works normally; no events are sent and no errors are shown. | assumption |

## 11. Rollout & experiment plan

Feature flag: `ai_chat_assistant_enabled` (source: assumption).

| Phase | Audience | Exposure | Exit criteria |
|---|---|---|---|
| Internal dogfood | Employee and test accounts | 0% | No P1/P2 defects; all events validated in the analytics debugger |
| Pilot | Nimbus Wireless or Nimbus Prepaid customers on app or web | 5% | Error rate and care contacts at or below baseline for 7 days |
| Ramp | Same | 50% | Primary metric not worse than control |
| General availability | All eligible customers | 100% | Experiment readout signed off |

Rollback: Turn off `ai_chat_assistant_enabled`; customers fall back to the current experience. Basis: A-3.

## 12. Test plan

| ID | Type | Title | Covers | Events verified | Expected |
|---|---|---|---|---|---|
| TC-1 | e2e | Verify FR-1 | FR-1, US-1 |  | There is a "Questions about your bill?" entry point on the bill page that opens the AI chat assistant |
| TC-2 | e2e | Verify FR-2 | FR-2, US-2 |  | The assistant receives the current bill period and account context so the customer does not have to re-explain when opened from the bill page |
| TC-3 | e2e | Verify FR-3 | FR-3, US-3 |  | The customer can escalate to a live care agent from the chat at any time |
| TC-4 | e2e | Verify FR-4 | FR-4, US-4 |  | The customer can rate each answer with thumbs up or thumbs down |
| TC-5 | analytics | Verify FR-5 | FR-5 |  | Track entry point views, chat opens, messages, escalations and ratings |
| TC-6 | e2e | Verify NFR-1 | NFR-1 |  | The assistant never displays full payment card or bank account numbers |
| TC-7 | performance | Verify NFR-2 | NFR-2 |  | The entry point is intuitive |
| TC-8 | accessibility | Verify NFR-3 | NFR-3 |  | All new UI on app or web meets WCAG 2.1 AA (screen-reader labels, 4.5:1 contrast, full keyboard/switch access) |
| TC-9 | analytics | Verify NFR-4 | NFR-4 |  | Tracking events contain zero PII: no names, phone numbers, free-text message content or full account/card numbers |
| TC-10 | analytics | Analytics: `ai_chat_assistant_entry_viewed` payload |  | `ai_chat_assistant_entry_viewed` | Fires exactly once with global properties and: entry_point, screen_name; values match the UI. |
| TC-11 | analytics | Analytics: `ai_chat_assistant_opened` payload | FR-1, FR-2 | `ai_chat_assistant_opened` | Fires exactly once with global properties and: entry_point; values match the UI. |
| TC-12 | analytics | Analytics: `ai_chat_assistant_message_sent` payload |  | `ai_chat_assistant_message_sent` | Fires exactly once with global properties and: message_count, message_length; values match the UI. |
| TC-13 | analytics | Analytics: `ai_chat_assistant_escalated` payload | FR-3 | `ai_chat_assistant_escalated` | Fires exactly once with global properties and: message_count, escalation_reason; values match the UI. |
| TC-14 | analytics | Analytics: `ai_chat_assistant_feedback_submitted` payload | FR-4 | `ai_chat_assistant_feedback_submitted` | Fires exactly once with global properties and: rating, answer_id; values match the UI. |
| TC-15 | performance | Verify NFR-5 | NFR-5 |  | The assistant responds quickly [measurable target for 'quickly' TBD: OQ-3] |

## 13. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Event names drift between app and web, breaking the cross-platform funnel | medium | high | Treat section 7 as the single source; lint against the event dictionary in CI. |
| Legal review changes what data can be used | medium | high | Start review now; design for the minimal data set. |
| 2 blocking open question(s) delay build start | high | medium | Review open questions with owners before sprint planning. |

## 14. Assumptions

| ID | Assumption | Validate with |
|---|---|---|
| A-1 | Accessibility follows the company default of WCAG 2.1 AA. | UX Design |
| A-2 | Analytics events must not carry PII; this is standard instrumentation policy. | Privacy / Analytics governance |
| A-3 | Rollout stages follow the standard flag-based ramp. | Release management |

## 15. Open questions

| ID | Question | Why it matters | Owner | Blocking |
|---|---|---|---|---|
| OQ-1 | What will Legal approve regarding how bill data is shared with the assistant? | Build cannot be finalised until the review outcome is known. | Legal | yes |
| OQ-2 | Should account sub-users (non-owners) see the entry point? | The request explicitly leaves this open; it changes scope or eligibility logic. | Product | yes |
| OQ-3 | What measurable target defines 'intuitive', 'quickly' in: "The entry point should be intuitive and the assistant should respond quickly"? | Without a threshold the requirement cannot be tested or accepted. | Analytics | no |
| OQ-4 | What is the target and timeframe for: "Reduce billing-related calls to care"? | Success metrics need a target to size the rollout and judge the launch. | Analytics | no |
| OQ-5 | Which care-contact data source and reason codes identify the calls in: "Reduce billing-related calls to care"? | The metric cannot be computed from app/web events alone. | Analytics | no |
| OQ-6 | What is the target and timeframe for: "Increase the share of bill-page chat sessions resolved without an agent"? | Success metrics need a target to size the rollout and judge the launch. | Analytics | no |
| OQ-7 | Is `ai_chat_assistant_opened` the same user action as existing `chat_assistant_opened`? If so, reuse the existing event. | Avoids two events for one action, which double-counts the funnel. | Analytics | no |
| OQ-8 | Is `ai_chat_assistant_message_sent` the same user action as existing `chat_assistant_message_sent`? If so, reuse the existing event. | Avoids two events for one action, which double-counts the funnel. | Analytics | no |

## Appendix A. Quality score

Deterministic rubric score: **99 / 100**.

| Category | Score | Max |
|---|---|---|
| Section completeness | 20 | 20 |
| User stories & acceptance criteria | 15 | 15 |
| Requirement quality | 20 | 20 |
| Tracking plan | 19 | 20 |
| Consistency & traceability | 15 | 15 |
| Ambiguity handling | 10 | 10 |

- **info** (NFR-2): Vague wording (intuitive) is deferred to an open question; resolve before build.
- **info** (NFR-5): Vague wording (quickly) is deferred to an open question; resolve before build.
- **warning** (ai_chat_assistant_opened): [dictionary:possible-duplicate] 'ai_chat_assistant_opened' is very similar to existing event 'chat_assistant_opened'.
- **warning** (ai_chat_assistant_message_sent): [dictionary:possible-duplicate] 'ai_chat_assistant_message_sent' is very similar to existing event 'chat_assistant_message_sent'.

## Appendix B. Event dictionary lint

Checked 5 events against 11 dictionary entries.

| Severity | Event | Rule | Finding | Suggestion |
|---|---|---|---|---|
| warning | `ai_chat_assistant_opened` | possible-duplicate | 'ai_chat_assistant_opened' is very similar to existing event 'chat_assistant_opened'. | Confirm with the dictionary owner whether this is the same user action. |
| warning | `ai_chat_assistant_message_sent` | possible-duplicate | 'ai_chat_assistant_message_sent' is very similar to existing event 'chat_assistant_message_sent'. | Confirm with the dictionary owner whether this is the same user action. |
