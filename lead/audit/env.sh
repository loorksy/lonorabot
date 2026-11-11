# Shared audit environment (test-only values).
export ROOT=/home/user/lonorabot
export LONORA_ENCRYPTION_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=
export LONORA_BOOTSTRAP_TOKEN=lonora-ui-reference-ci-only-2026
export LONORA_COOKIE_SECURE=false
export LONORA_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/lonora_audit_ci
export LONORA_ALLOWED_ORIGIN=http://localhost:8832
export LONORA_WEB_ROOT=$ROOT/.runtime/ui-reference-web
export LONORA_CHART_RENDERER_ROOT=$ROOT/.runtime/ui-reference-web
export LONORA_ARTIFACT_ROOT=$ROOT/.runtime/ui-reference-artifacts
export LONORA_UI_TEST_EMAIL=ahmed@example.com
export LONORA_UI_TEST_PASSWORD=ci-only-owner-password
export LONORA_UI_TEST_BROWSER_PATH=/usr/bin/google-chrome
export NODE_ENV=production
PP=""; for d in $ROOT/packages/*/src $ROOT/apps/*/src; do PP="$PP:$d"; done; export PYTHONPATH=${PP#:}
unset AI_AGENT CLAUDECODE
