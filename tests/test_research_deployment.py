"""Mandate 13.1: web search and the research browser are on in the production stack.

They used to start only from an optional overlay that the installer left out, so a stock
installation had no `web_search` and no `web_browse`.
"""

import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROD = ROOT / "infra/compose/docker-compose.prod.yml"


def stack() -> dict[str, Any]:
    return yaml.safe_load(PROD.read_text())


def test_the_production_stack_runs_web_search_and_the_research_browser() -> None:
    services = stack()["services"]
    gateway = services["gateway"]
    assert (
        gateway["environment"]["LONORA_SEARXNG_URL"] == "${LONORA_SEARXNG_URL:-http://searxng:8080}"
    )
    assert (
        gateway["environment"]["LONORA_BROWSER_URL"] == "${LONORA_BROWSER_URL:-http://browser:8090}"
    )
    assert set(gateway["networks"]) == {"default", "research"}
    assert services["searxng"]["networks"] == ["research"]
    assert services["browser"]["networks"] == ["research"]
    assert services["browser"]["command"] == ["python", "-m", "lonora_tools.browser_service"]
    assert (PROD.parent / services["searxng"]["volumes"][0].split(":")[0]).resolve() == (
        ROOT / "infra/research/searxng.yml"
    )
    # The overlay that kept them off is gone, and nothing points at it.
    assert not (ROOT / "infra/research/compose.research.yml").exists()
    for path in ("infra/compose/install.sh", "docs/operations.md", ".env.example"):
        assert "compose.research.yml" not in (ROOT / path).read_text()


def test_research_services_stay_isolated_and_never_hold_the_gateway() -> None:
    services = stack()["services"]
    for name in ("searxng", "browser"):
        service = services[name]
        # No database network, no application secrets or volumes, no host ports.
        assert "env_file" not in service and "ports" not in service
        assert all(":/app" not in volume for volume in service.get("volumes", []))
        assert service["cap_drop"] == ["ALL"] and service["read_only"] is True
        assert service["mem_limit"] and service["cpus"]
    # Only the gateway joins their bridge; the database, API and Caddy never do.
    for name in ("db", "api", "migrate", "caddy"):
        assert "research" not in services[name].get("networks", ["default"]), name
    # Trading must not wait on search: a gateway that depends on them would not start
    # (and would not reconcile orders) while SearXNG or the browser is unhealthy.
    assert set(services["gateway"]["depends_on"]) == {"api"}


def test_lonora_never_waits_on_web_search_and_drops_the_retired_overlay() -> None:
    script = (ROOT / "infra/compose/lonora").read_text()
    # `compose up --wait` without a service list waits on every service, search included:
    # an unhealthy SearXNG would then fail an update (and roll it back), a restore or a start.
    for line in script.splitlines():
        if "compose up" in line and "--wait" in line:
            assert "--wait db" in line or '"${CORE_SERVICES[@]}"' in line, line
    assert "CORE_SERVICES=(db api caddy gateway)" in script
    assert "RESEARCH_SERVICES=(searxng browser)" in script
    # An installation that listed the old overlay stops merging it on its next update.
    assert "RETIRED_OVERLAYS=(infra/research/compose.research.yml)" in script
    assert "    retire_overlays\n}" in script


def run_retire(tmp_path: Path, env: str) -> tuple[str, str]:
    """Run the script's own retire_overlays on a scratch .env (no Docker needed)."""
    (tmp_path / ".env").write_text(env)
    (tmp_path / ".env").chmod(0o600)
    functions = (
        "set -euo pipefail; say() { printf 'lonora: %s\\n' \"$*\"; }; "
        "source <(sed -n -e '/^env_value() {/,/^}/p' -e '/^RETIRED_OVERLAYS=/p' "
        "-e '/^retire_overlays() {/,/^}/p' " + str(ROOT / "infra/compose/lonora") + "); "
        "retire_overlays"
    )
    done = subprocess.run(
        ["bash", "-c", functions], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    return (tmp_path / ".env").read_text(), done.stdout


def test_an_update_drops_only_the_retired_overlay_and_keeps_every_secret(tmp_path: Path) -> None:
    before = (
        "LONORA_ENCRYPTION_KEY=secret-value\n"
        "LONORA_COMPOSE_OVERLAYS=infra/research/compose.research.yml "
        "infra/analysis/compose.workspace.yml\n"
        "LONORA_DOMAIN=example.com\n"
    )
    after, said = run_retire(tmp_path, before)
    assert after.splitlines() == [
        "LONORA_ENCRYPTION_KEY=secret-value",
        "LONORA_DOMAIN=example.com",
        "LONORA_COMPOSE_OVERLAYS=infra/analysis/compose.workspace.yml",
    ]
    assert "removed from LONORA_COMPOSE_OVERLAYS" in said and "secret-value" not in said
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    # Nothing to drop: the file is left exactly as it was.
    untouched = "LONORA_ENCRYPTION_KEY=x\nLONORA_COMPOSE_OVERLAYS=\n"
    assert run_retire(tmp_path, untouched) == (untouched, "")
