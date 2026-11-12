# sweep/14-notes-tool at 5edf837f (W-SWEEP; no PR number yet)

- Branch: `sweep/14-notes-tool`
- Head: 5edf837f. Commits: 3c9ce885, 5edf837f.
- Base: 40183fb6. It merges cleanly with main 6cb4421d.
- Verdict: **FINDINGS** (0 high, 1 medium, 3 low)

## Verified findings

### M1 (medium): `knowledge_note_add` with `replaces` removes the old note without a trace
- **Where:** `packages/tools/src/lonora_tools/knowledge.py:28,76` passes `replaces` to `lonora_memory.semantic.index_note`.
  - In `semantic.py`, the event is emitted only when the new text creates a new row (`if row is None: … emit("knowledge_notes.updated" if replaces else "knowledge_notes.created")`).
  - The old row is then deleted unconditionally (`if replaces and replaces != document_id: … session.delete(old)`).
- **Effect:**
  - When the new text equals another existing note, the replaced note disappears and no event is written.
  - Even in the normal case, the `updated` event carries only the new id. It has neither the replaced id nor its text.
  - An agent can thus erase a note the owner wrote without any record. This contradicts 5edf837f's "every write and removal is attributed" and the delete tool's "a removal leaves a trace".
- **Probe** (reviewer, with the PR's fixtures): add «Owner rule A» and «Rule B», then `knowledge_note_add({"content":"Rule B","replaces":<A>})` → rows `['Rule B']`; events: two `knowledge_notes.created` only.
- **Fix:** whenever `replaces` deletes a row, emit `knowledge_notes.deleted` (or `replaced: {id, text}` in the update event) with `written_by`, as `knowledge_note_delete` does. Do this whether or not the new row already existed, and test both cases.

### L1 (low): the delete tool's description claims a condition the code does not check (0.4)
- **Where:** `knowledge.py:143` says "Remove one knowledge note by id when the owner asks". Neither delete nor `replaces` checks `owner_message_id`, and `observe_only` wakes and peer-started runs may call them.
- **Fix:** gate deleting or replacing an owner-written note on `owner_message_id`, as `memory_write` does for the owner profile; or word the description as the code behaves.

### L2 (low): a note's origin is stored but never shown (6.10 provenance)
- `written_by` is saved in the payload, but recall still labels every note `source: legacy_unknown` (`lonora_memory/evidence.py:256-262`).
- `knowledge_items` (`lonora_db/knowledge.py`) drops the field, so neither `knowledge_note_list` nor the owner's «المعرفة» can tell an agent's note from the owner's. No `source_message_id` is recorded, unlike `memory_write`.
- Recall still frames notes as untrusted data, so the data-versus-instruction rule holds.
- **Fix:** project `written_by` (and the run's `owner_message_id`) into the evidence provenance and the list rows.

### L3 (low): the private-memory test does not cover the new path
- **Where:** `tests/test_private_memory.py` asserts a team agent's memory is unreachable "through every path an agent has". `knowledge_note_list` and `knowledge_note_add` are new paths and are not in it. The PR's own test covers the peer refusal.
- **Fix:** add both tools to that test's peer-refusal and Lonora-reach cases.

## Rejected candidates
- **"Lonora writing another agent's notes exceeds 3.1.6 ('MAY read')":** 3.1.2 ("give them responsibilities and instructions", "edit their methods") reasonably covers it. This is an interpretation question, not a defect.
- **"Notes are not secret-redacted (7.2.6)":** tool and workspace output is already redacted before the model sees it, and `memory_write` behaves the same. No leak shown.
- **"The activity log does not list `.deleted` and `.updated`":** consistent with the existing route delete. Not new.

## What I checked
- **5.8.6:** `manifest.json` lists the three tools under "memory". `export_agent_tool_reference.py --check` passes.
- **Classification:** run-evidence treats add and delete as skipped and list as external.
- **Arabic:** search terms are present.
- **Access:** peers are refused (`knowledge_note_agent_not_allowed`). Delete and replace re-check the row's agent. The Lonora check is the built-in role (14.3.15).
- **Scope:** no Stop or section 6 change, no new screen, no migration.
- **Tests:** `test_knowledge_tool`, `test_context_engine`, `test_capability_exposure`, `test_skill_runtime`: 114 passed.
