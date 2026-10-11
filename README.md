# Lonora

Lonora is a Python-first platform for persistent AI agents. Agents retain durable identities, conversation history, and long-term memory; a separate worker executes queued and scheduled work so agents keep running when the browser is closed. The initial model adapter targets xAI Grok through its OpenAI-compatible API. The application is an independent implementation inspired by persistent-agent systems; it does not reuse their source code.

The project is being built from a clean `main` history using the requirements in [`docs/`](docs/). The first milestone establishes the durable backend foundation: FastAPI, async SQLAlchemy, PostgreSQL, Alembic migrations, lease-based run recovery, and interval routines. The full product plan also includes a React/TypeScript Arabic-first RTL client, global model routing, collaboration, tools, market research, safely gated trading, and realtime voice. Those capabilities will be delivered in subsequent milestones; they are not represented as complete here.

## Run locally

Requires Python 3.12+, Docker Compose, and Git.

```bash
cp .env.example .env
docker compose up -d db
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
uvicorn lonora.api:app --reload --host 127.0.0.1 --port 8000
```

Run the persistent worker in a second terminal:

```bash
. .venv/bin/activate
python -m lonora.worker
```

The model key is optional for startup but required for generated responses. Set `LONORA_MODEL_API_KEY` through your shell or secret manager. Never commit credentials. The default global provider is xAI, with `grok-4.20-0309-non-reasoning` as the configured model. The endpoint and model can be changed without per-agent overrides.

Check `GET /health`; interactive API documentation is at `/docs`. A basic conversation flow is:

1. `POST /agents` with `{"name":"Lonora","instructions":"..."}`.
2. `POST /agents/{agent_id}/threads` with `{"title":"First conversation"}`.
3. `POST /threads/{thread_id}/messages` with `{"content":"Hello"}`. This returns a durable run ID.
4. Poll `GET /runs/{run_id}` and read messages from `GET /threads/{thread_id}`.

Memory is available through `GET` and `PUT /agents/{agent_id}/memory`. Create a recurring task through `POST /agents/{agent_id}/routines`; the worker enqueues due work.

## Configuration

Settings use the `LONORA_` environment prefix and can be set in `.env` for local development:

- `LONORA_DATABASE_URL` — async PostgreSQL URL; local Compose default is `postgresql+asyncpg://lonora:lonora@127.0.0.1:5432/lonora`.
- `LONORA_MODEL_BASE_URL` — OpenAI-compatible endpoint; defaults to `https://api.x.ai/v1`.
- `LONORA_MODEL_NAME` — global model identifier.
- `LONORA_MODEL_API_KEY` — server-side provider secret.
- `LONORA_WORKER_POLL_SECONDS` — queue polling interval; defaults to `0.5`.
- `LONORA_RUN_LEASE_SECONDS` — claim lease and stale-run recovery interval; defaults to `150`.

## Development

```bash
ruff check .
pytest
```

Database changes are versioned in `migrations/`. Do not use ORM `create_all` in deployed environments; apply migrations with `alembic upgrade head`.

## Product scope

The project profile and architecture in `docs/` describe the target system. Features that need external services or credentials (model providers, broker data, LiveKit) remain gated until configured. Real-money trading must remain disabled by default and go through explicit global controls, idempotent execution, and an auditable journal.
