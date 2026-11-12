"""Mandate 13.1: web search and the research browser are on in the production stack.

They used to start only from an optional overlay that the installer left out, so a stock
installation had no `web_search` and no `web_browse`.
"""

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
    assert gateway["environment"]["LONORA_SEARXNG_URL"] == "http://searxng:8080"
    assert gateway["environment"]["LONORA_BROWSER_URL"] == "http://browser:8090"
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
    # Trading must not wait on search: a gateway that depends on them would not start
    # (and would not reconcile orders) while SearXNG or the browser is unhealthy.
    assert set(services["gateway"]["depends_on"]) == {"api"}
