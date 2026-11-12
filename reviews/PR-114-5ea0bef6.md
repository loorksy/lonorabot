# PR #114 at 5ea0bef6: FINDINGS (0 high, 0 medium, 1 low)

- PR: #114, "W-OWNER 6: pin private memory with tests (3.2.4)" (W-OWNER)
- Head: 5ea0bef644265ff23f0896cadc4d11eba7b8effc
- Base: main (merge-base 2a244c8c). Merges cleanly with current main 4d4348ae.
- Reviewer: R-AGENT, 2026-11-12T06:53Z
- Verdict: FINDINGS

## Finding 1 (low): the static pin misses attribute access to the memory store

- File: `tests/test_private_memory.py:53-60` (`test_no_workspace_module_touches_the_memory_store`).
- Evidence: the test collects only `ImportFrom` alias names and bare `ast.Name` ids. A workspace module that reads memory through a module attribute passes. Probe: I added `packages/zzprobe/src/zz_workspace/export.py` containing `from lonora_db import memory` and `await memory.read_memory(s, o, a)`. The test then reported `1 passed`. The probe was removed afterwards.
- Fix: also collect `node.attr` for every `ast.Attribute`, plus the module names of `Import` and `ImportFrom`. Fail when a workspace module imports `lonora_memory` or `lonora_db.memory`, or names any member of `MEMORY_STORE` as an attribute.

## Rejected candidates

- The `agent_inspect` assertion `!= "None"` is weak: rejected. A successful result has no `code`, so it maps to `"None"` and the assertion fails. The assertion therefore does require a refusal.

## What was checked

- Mandate 3.2.4: the PostgreSQL test reads one team agent's memory through memory_read, search_internal, session_search, subagent_inspect and agent_inspect from the agent itself, from Lonora and from another team agent, and through the owner API.
- The PR is test-only: no code, prompt or migration changes.
- `tests/test_private_memory.py` passes on a fresh database (2 passed).
