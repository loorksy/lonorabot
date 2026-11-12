# sweep/14-notes-tool at 895c4fa9 (re-review of the new commit only)

- Branch: `sweep/14-notes-tool` (no PR number yet)
- Head: 895c4fa9. Previous review: 5edf837f (`PR-sweep-14-notes-tool-5edf837f.md`).
- Reviewed: 5edf837f..895c4fa9.
- Verdict: **CLEAN**

## Previous findings
- **M1 fixed.** `index_note` emits `knowledge_notes.deleted` whenever `replaces` removes a row, with the old id, its text (up to 8000 characters), `replaced_by` and `written_by`. This also covers the case where the new text matched an existing note and no created or updated event is written. Tests were added in `tests/test_knowledge_tool.py`.
- **L1 fixed.** The delete description now says what the code does: "The removal is recorded with who removed it."
- **L2 fixed.**
  - Recall labels an agent-written note `{"source": "agent_note", "agent_id": …}` and keeps `authority: untrusted_memory_content`. The owner's and older notes stay `legacy_unknown`.
  - `knowledge_items` returns `written_by`, so the list and «المعرفة» can show it.
- **L3 fixed.** `tests/test_private_memory.py` covers `knowledge_note_list` and `knowledge_note_add` for peer refusal and Lonora's reach.

## What I checked
- pytest `test_knowledge_tool`, `test_private_memory`, `test_context_engine`, `test_capability_exposure`, `test_memory_retrieval`: 123 passed (fresh DB).
- `export_agent_tool_reference.py --check`: passes.
