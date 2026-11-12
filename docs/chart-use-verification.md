# Chart Use integration and verification

This documents the implemented chart capability, not completion of the full Agent-environment program.

## Runtime path

`chart_open / chart_set_* / chart_*indicator / chart_annotate`
→ current owner/Agent/account/exact-symbol guards
→ current Run fence
→ chart configuration + scoped effect receipt in one PostgreSQL transaction
→ immutable configuration acknowledgment.

`chart_inspect / chart_read_indicator / new chart_snapshot`
→ read current saved scene
→ if initializing, one attempt through the existing chart-refresh lease
→ current scene or explicit busy/source failure.

A ready scene is reused; actual failed-source codes are preserved. Gateway market/chart maintenance continues without a Web client. A configuration acknowledgment does not contain frozen market evidence. An old chart without an original creation receipt cannot prove the original action; list/inspect it before deciding whether to create another chart.

`chart_snapshot(renderer="tradingview", chart_id=..., locale="en"|"ar")`
→ authorized immutable scene
→ optional bounded server browser
→ the same licensed renderer used by Web/Mobile
→ exact applied scene/data revision acknowledgment
→ original PNG + immutable artifact provenance.

`artifact_read(artifact_id=..., view_image=true)`
→ scoped/hash-verified raster
→ actual pixels in the same Run's global VISION request.

Default snapshot renderer remains `semantic`; its PNG/SVG comes from backend scene drawing and must not be labeled a TradingView screenshot. Snapshot replay returns original bytes/provenance even after later chart edits. Saved, model-inspected, attached and client-rendered are separate facts.

## Operator configuration

The existing API serves `/charts/render` and its namespaced assets from the normal Web build. If using a separate Expo Web root, `LONORA_CHART_RENDERER_ROOT` points to the same built Web renderer.

- `LONORA_CHART_RENDERER_URL`: exact trusted operator URL ending in `/charts/render`. No user information, query or fragment. Production Compose sets `http://api:8000/charts/render`.
- `LONORA_CHART_BROWSER_EXECUTABLE`: installed Chromium executable. Production Compose sets `/usr/bin/chromium`.
- `LONORA_CHART_BROWSER_SANDBOX`: defaults true. Existing restricted production containers configure false while retaining dropped capabilities and no-new-privileges; no privileged container or added host capability is required.

Python installs pinned Playwright1.58.0. Both server Dockerfiles include Chromium and fonts. Captures are lazy and bounded; unset renderer URL leaves browser snapshots explicitly unconfigured while semantic snapshots remain available. No container image or APK was built during this implementation.

The browser has a private temporary profile/minimal environment, fresh credential-free contexts and static same-origin GET allowlists. API, external network, mutation and WebSocket requests are denied. Agent input cannot specify a URL, script or shell command. The trusted Playwright driver inherits the host environment through its public startup API; browser processes do not inherit provider/DB/VPS/proxy secrets.

## Verification

Run in the configured development environment with disposable PostgreSQL, never a production database or live-money test account:

- `pnpm --filter @lonora/web build` verifies the pinned vendor asset hashes and builds the shared renderer.
- `.venv/bin/pytest -q` exercises unit/runtime cases; real browser cases require the built renderer and Chromium.
- `.venv/bin/python tests/run_foundation_checks.py --isolated-databases` provisions separate disposable databases for registered integration fixtures, including creation/update receipts, snapshot provenance, Skills authority and conversation recall.
- `.venv/bin/python tests/check_chart_visual_observation.py` is the explicit additional PostgreSQL + real Chromium acceptance; configure it with a fresh migrated disposable database.

Recorded acceptance includes four exact forex/metal/index/crypto symbols and multiple frames, EN/AR, immediate native open→snapshot, original receipt replay, concurrent same-call creation, owner edits, worker death/new fence, stale-worker denial, actual PNG admission into a scripted model request, network restrictions and bounded cleanup.

No actual external-model understanding, live broker mutation, production deployment, native hardware behavior or permanent visual desktop is certified. Persistent interactive chart workspaces/navigation and broader quality evaluation remain open.
