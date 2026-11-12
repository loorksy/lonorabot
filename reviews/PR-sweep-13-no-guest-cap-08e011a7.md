# sweep/13-no-guest-cap at 08e011a7 (W-SWEEP; no PR number yet)

- Branch: `sweep/13-no-guest-cap`
- Head: 08e011a7. Commits: a0ef4421, 08e011a7.
- Base: 40183fb6 (rebase before merge; main is 6cb4421d).
- Verdict: **FINDINGS** (0 high, 1 medium, 2 low)

## Removed limits, classified
| Limit | Verdict |
|---|---|
| `MAX_DIRECT_GUESTS = 2` / `collaboration_guest_limit` | Cap on agents. Removal correct (P1, 3.3.2). |
| `mention_agent_ids` max 16 | Cap. Removal correct. |
| `participant_ids` max 16 / `collaboration_participant_limit` | Cap. Removal correct. |
| group `member_ids` max 12 | Cap. Server and AddMembers removed; see M1. |
| `participant.run_ids >= 64` | Redundant under the rounds bound. Removal fine. |
| rounds per session ≥ 8 | Runaway guard, kept (`MAXIMUM_ROUNDS`). Correct. |

**No unbounded loop.** "Start a new collaboration when one is full" resets the per-session rounds, but agent-started chains stay bounded by:
- `invite()`'s ancestry walk (`delegation_depth_exceeded` after 4 ancestors);
- `require_collaboration(depth, maximum=3)`;
- `peer_cycle`.

Synthesis runs carry `parent_run_id`. An agent could already omit `session_id` before this branch.

## Verified findings

### M1 (medium): the web New Group page still caps a group at 12 (P1, 3.3.2, 14.1.4)
- **Where:** `apps/web/src/shell/agent/GroupPage.tsx:332` (`NewGroupPage`): `disabled={!picked.includes(agent.id) && picked.length >= 12}`.
- The server cap and AddMembers' cap are removed, and 08e011a7 says "no group member cap", but creating a group on web still blocks the 13th agent. Mobile has no cap.
- **Fix:** drop the condition, and add a web test that picks more than 12 agents on the New Group page.

### L1 (low): no test shows the kept runaway guard still refuses
- No test asserts `collaboration_round_limit` (grep: no hits in tests/). The guard is the reason the remaining bound is allowed under 3.3.2.
- **Fix:** fill `MAXIMUM_ROUNDS`, call `collaboration_start` with that `session_id` from an agent, and expect 409.

### L2 (low): the tool description hardcodes "8 rounds"
- **Where:** `packages/tools/src/lonora_tools/collaboration.py:120`. Elsewhere the code uses `MAXIMUM_ROUNDS`.
- **Fix:** build the description from the constant.

## Unverified (traced only, not counted)
- **A stale full `session_id`:** an owner `@all` that passes one opens a new session per message (`messages.py:635`). Two concurrent sends make two sessions, and the full one stays `collaborating`. No money or safety impact.
- **Duplicate mentions:** `mention_agent_ids` is no longer bounded and is not deduplicated before one `owned_agent` query per id under the thread lock (`messages.py:332`). Suggest `dict.fromkeys(...)`.

## What I checked
- **Concurrency:** `send_message` and the tool both hold the host-thread lock, and `invite()` reads the session `FOR UPDATE`.
- **Replay:** stable via client_nonce and `stable_id(host_run.id, "collaboration:" + message.id)`.
- **Section 6:** untouched.
- **14.3.9:** `CollaborationState` constraints are only loosened. No migration is needed.
- **5.8.6:** the manifest hash is regenerated for the `lonora.md` edit, and `export_agent_tool_reference.py --check` passes.
- **0.4:** no leftover `MAX_DIRECT_GUESTS`, `collaboration_guest_limit` or `collaboration_participant_limit`.
- **14.1.4:** core, web and mobile are updated, apart from M1.
- **Arabic:** new text has Arabic on mobile and web (web i18n 0 missing ar).
- **Tests are made positive, not weakened:** 3- and 17-guest messages, full-session rollover, an 18-member group.
- **Runs at the head:**
  - pytest `test_conversation_conveniences` + `test_system_policy`: 28 passed.
  - Checks `check_collaboration_sessions`, `check_runtime_collaboration`, `check_group_replies`: all pass.
  - tsx chat-rows and mention-session: 17/17. tsc core, web and mobile: clean.
  - Playwright web agent-pages, chat-lists, group-status: 39/40. `group-status.spec.mjs:14` fails identically at the base 40183fb6.
