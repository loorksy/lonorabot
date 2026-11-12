# PR #100 — W-MODELS 2 re-review at ea0e8fe5

- Head: ea0e8fe5; new commit ea0e8fe ("a credentials file joined from parts, and the engine named in a variable")
- Reviewer: R-SEC
- Verdict: **CLEAN**
- The earlier L1 is fixed. Mutation re-run on a `git archive` copy:
  - `Path.home()/".claude"/".credentials.json"`: CAUGHT;
  - `ENGINE = "claude"; subprocess.run([ENGINE, "-p", prompt])`: CAUGHT;
  - `from claude_agent_sdk import query`: CAUGHT;
  - legitimate `subprocess.run(["claude", "--version"])`: not flagged.
- `tests/test_model_access_guard.py`: 48 passed. It runs in CI (`ci.yml`).
