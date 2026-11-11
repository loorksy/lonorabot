LONORA WORKER SESSION — shared rules (binding)

You are one of five worker sessions building Lonora (repository loorksy/lonorabot) in parallel. The lead session is session_0111sgouu67WYk3Zo9wPCpEY: it coordinates, reviews and merges. Report to it with the send_message tool (session_id session_0111sgouu67WYk3Zo9wPCpEY): a short message when you start, at each milestone, when blocked, and when your PR is open (PR number, what it delivers, verification results, deviations). Never merge a PR, never push to main, never push to any branch but your own.

Binding documents, in this order (they win over anything else): docs/ui-reference/OWNER_DECISIONS.md (Q1-Q59 and the standing rules: the team decides UI questions itself within the reference and these decisions, and asks the owner only on a genuine conflict; the agent decides each answer's shape), docs/lonora-specs/MANDATE_CORRECTIONS.md, VISION.md, docs/ui-reference/CAPABILITY_MAP.md, docs/ui-reference/Lonora-Desktop-37.html (the single source of truth for look and behaviour of apps/web), AGENTS.md, CLAUDE.md. Money-safety invariants are untouchable: money moves only through the signed grant or an approval card at the single executor; no UI, card, tool or prompt may place, change or approve a trade, or widen authority or limits. Agents and groups are never deleted from the UI (Q1, Q44). Arabic first, RTL, the reference's own terms only; Lingui ar/en with 0 missing Arabic. The avatar stays Lonora's existing avatar component, placed where the reference shows avatars.

Fresh-container setup (run once; restart PostgreSQL after any container restart):
  service postgresql start
  su postgres -c "psql -c \"CREATE ROLE lonora LOGIN SUPERUSER PASSWORD 'ci-only-password'\"" || true
  python3.12 -m venv .venv && .venv/bin/pip install -q -e '.[dev]'
  .venv/bin/python scripts/cache_model_tokenizers.py
  env -u AI_AGENT -u CLAUDECODE pnpm install --frozen-lockfile
  export LONORA_ENCRYPTION_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= LONORA_BOOTSTRAP_TOKEN=ci-only-bootstrap-token-32-characters LONORA_COOKIE_SECURE=false
  Test databases: CREATE DATABASE <name>_test (or _ci for Playwright) OWNER lonora; LONORA_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/<name>; bash scripts/migrate.sh. Drop them when done.
Every pnpm/turbo command MUST be prefixed with `env -u AI_AGENT -u CLAUDECODE` (otherwise turbo rewrites AGENTS.md); `git diff --quiet -- AGENTS.md` must hold.

Verification regime (the owner asked for speed): while writing, run only fast checks (ruff, pyright on touched files, the unit tests of the module you changed, tsc). Write tests first for money-safety and security code. At the end, ONCE: full `pytest tests -q` on a fresh *_test DB; `pnpm lint`, `pnpm check`, `pnpm build`, `pnpm --filter @lonora/web i18n`; the check_*.py scripts your change touches; the full Playwright web suite (`LONORA_UI_TEST_BROWSER_PATH=/usr/bin/google-chrome`, fresh *_ci DB). Known baseline Playwright failures to ignore: agent-permissions:391, group-status:14, skills-management:121, visual-response:64 x4. GitHub CI is down (billing lock), so this local run is the gate; report it honestly with numbers.

Migrations: use only your reserved revision ids (given in your task), chained to the current head on main (0045_chat_lists); the lead re-chains at merge. Translation catalogs: run the extraction; the lead regenerates on conflicts.

Git: commit early and in logical commits; push your branch at every milestone (containers restart). End commit messages and the PR body with the attribution lines your own session gives you. When done, open a PR into main with: Summary, Backend (tables, routes, migrations), Web, Verification (table), Remaining deviations. Then send the lead the PR number and stop. If the lead messages you with review findings, fix them on the same branch.
