# PR #100 — W-MODELS 2 re-review at 5dec7ce1

- Head: 5dec7ce1. New since 987943e5: the merge of main (cd09bed), then 5dec7ce ("wider scan, stored-login and OAuth rules, real process starts, CI")
- Reviewer: R-SEC
- Verdict: **FINDINGS** (0 high / 0 medium / 1 low)

## Status of the earlier findings
- M1 (not in CI): **fixed.** `ci.yml:846` runs `pytest tests/test_model_access_guard.py`.
- M2 (credential reuse slipped through): **mostly fixed.** I re-ran the mutation set on a `git archive` copy. Caught now:
  - `~/.codex/auth.json`, the keychain item `Claude Code-credentials`;
  - `auth_token=`/`ANTHROPIC_AUTH_TOKEN`, `claude-code-20250219`;
  - `platform.claude.com/v1/oauth/token`, `claude.com/cai/oauth`, `api.anthropic.com/api/oauth/…`.
- M3 (deployment files skipped): **fixed for engine use.** `analytics.requirements.lock` (`claude-agent-sdk==0.1.0`), `infra/compose/lonora` (`exec claude -p`) and `infra/systemd/*.service` are caught.
  - `npm i -g @anthropic-ai/claude-code` in `infra/analysis/analytics.Dockerfile` or `scripts/install.ps1` is deliberately allowed as workspace tooling (12.2, 7.1), with a test. Accepted.
- L1 (process-start bypasses and over-reach): **fixed** for `shell=True` f-strings, an absolute `/usr/local/bin/claude` argv and TS `execSync` templates. The over-reach samples (`["claude","--version"]`, a chatgpt.com link, `/auth/setup-token`, a langgraph comment) are now explicitly not flagged.

## Remaining finding

### L1 (low): two indirections still slip through
- The test still passed with each of these:
  - `Path.home()/".claude"/".credentials.json"`: the rule `\.claude/\.credentials\.json` needs the joined path;
  - `ENGINE = "claude"; subprocess.run([ENGINE, "-p", prompt])`.
- Fix: also match the file name `\.credentials\.json` next to `\.claude` within one statement (or just `["']\.credentials\.json["']`), and a module constant assigned `"claude"`/`"codex"` that is used as argv[0].

## What I checked
- `tests/test_model_access_guard.py` at head: 43 passed.
- Mutation results: 14 of 16 engine and credential cases are caught; the two remaining are above.
