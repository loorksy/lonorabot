# What was built or planned before the mandate: keep / change / drop

Lead's mapping, 2026-11-12. The mandate (`VISION.md`) wins everywhere. "Phase N" = the mandate's phase table.

## Merged work (stays in main)
| Item | Verdict | Why / where it goes |
|---|---|---|
| Harness 3a: error contract, one resolver, durable symbol map | keep | Section 17 (no raw codes or ids in normal views, durable runs). |
| Harness 3b: conversation gate (structural end-of-turn conditions) | keep | Nothing in the mandate touches it; it limits no trading decision. |
| Harness 3c: bound choices on a question, the tapped choice is checked | keep the runtime, change the surface | 10.1.2: no fixed card type for questions. The wait/answer mechanism stays; the question is drawn by the agent as a composition once v2 is the default (after phase 2). A composition's submission is input to judgment (6.10), so the "tap carries out exactly what was bound" check stays as a correctness aid, never as an approval. |
| Agent eval harness (`scripts/agent_eval`) | keep, re-target | Becomes the harness of the acceptance scenario (section 16). |
| GenUI v2 (web renderer, compile, projector) | keep | Phase 2 makes it the default. |
| Grants, limits, restrictions, goals, supervision, ladder (Wave 1, W15) | drop in phases 3 and 6 | Sections 4.4, 14.2. Survivors per 14.3. |
| Owner actions cards | change | 10.3.2 mapping: five fixed cards + typed owner message. |
| Workspace jobs (45 s, no network) | replace in phase 4 | Section 7. |

## Unmerged work
| Item | Verdict | Why |
|---|---|---|
| UI branch `ccr-9c66a289-3283wb` (106 commits, conversation UI of Reference-37) | land it (W-UI) | Owner's "no work wasted" and P7. Chat is the control surface (P5), so the conversation, composer, lists and message work is the product's main screen. |
| Screens outside conversations on that branch (settings pages, chat preferences page, agent pages, sheets for permissions and limits) | drop later | P5 allows six things outside conversations. Each goes in the phase that gives its chat replacement (permissions and limits: phase 3; agent pages, model, supervision: phase 6; the rest with phases 6-8). |
| Reference-37 wave 2 (forms, permission sheet, cleanup), positions/orders home, new-agent flow screens | drop | Out-of-chat screens the mandate removes; agents are created from chat by Lonora (3.1.2). |
| Rich message content, icons | keep, inside phase 2 | They are the clay's component catalog and tokens (10.1.1). |

## Planned, not started (the old lists)
| Item | Verdict | Where |
|---|---|---|
| 3c-2 open requests; 3c-3 a Task asks in the owner's chat, a failed watch says so once | fold | Phase 7 (routine output in the agent's own conversation, silence, the attention view). |
| 3d owner scope (owner-words gates) | change | 14.3.5 fixes exactly where `owner_message_id` still gates: tickets the agent does not own, reach-me settings, trusting a source, model assignment. Phases 3 and 6. |
| 3f reply guard, number provenance, language | fold | Phase 5 (5.3.3: never state a profit the account does not show or an execution the broker has not confirmed). |
| 3e the 45 owner actions that have no tool | keep | P5: everything else is done from chat. Each action gets its tool in the phase of its area (6, 7, 8). |
| 3g mandate defaults, targets, plan | drop | Belonged to grants and goals. |
| Final live evaluation, replay on the demo account, before/after report | replace | Section 16 acceptance scenario on a MetaApi demo account. |

## Documents
`docs/research/OWNER_BRIEF.md`, `docs/agent-harness-plan.md`, `docs/ui-reference/OWNER_DECISIONS.md`,
`docs/lonora-specs/MANDATE_CORRECTIONS.md` and the old `VISION.md` are superseded (phase 1 marks them).
