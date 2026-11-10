# Usage dashboard data

The «الاستهلاك» page and the model page's 7-day bars read model usage as a view of what
requests cost at list price. There is no spend cap, budget or limit anywhere (owner
decisions D4 and Q22): the month card shows the month to date and a projection, never a
meter against a limit, and nothing here ever blocks a request.

## Where the numbers come from

Every model call writes one `ln_usage` row (`lonora_llm_usage.store.save_usage`): the
run, provider, model and the provider's `TokenUsage` (`input_tokens`, `output_tokens`,
`cached_tokens`) in the JSON payload, with `owner_id`, `agent_id` and `created_at`.

Cost is priced at read time from `lonora_core.model_pricing` (USD per million uncached
input, cached input and output tokens, recorded on `PRICES_AS_OF`). Old rows are priced
the same way as new ones; nothing is stored per row.

- Anthropic reports `input_tokens` without the cache reads; the OpenAI-compatible APIs
  (OpenAI, DeepSeek, Z.ai, OpenRouter) include the cached tokens in `prompt_tokens`. The
  dashboard normalizes: `input_tokens` is every prompt token, cached included, and
  cached tokens are priced once, at the cached rate.
- A model the table does not name has no cost: `cost_usd` sums the priced requests and
  `unpriced_requests` counts the rest. Only a dated snapshot of a listed model is priced
  as that model; a variant (`-mini`, `-pro`, a new version) needs its own row.
  OpenRouter ids are not priced.
- Not modelled (the shown cost is a lower bound): cache writes (not recorded by the
  adapters), long-context premium tiers, batch/priority tiers and fast mode.

## Windows

Times are in the owner's zone: the `tz` query parameter (an IANA name, 422
`invalid_timezone` otherwise), else the reach-me preference's `timezone`, else UTC.

| period | bucket | points | window |
|---|---|---|---|
| `day` | hour | 24, today; hours not started are null | today 00:00 to now |
| `week` | day | 7 | 6 days ago 00:00 to now |
| `month` | day | 30 | 29 days ago 00:00 to now |

`previous` is the equal window just before, cut at the same wall-clock time (for `day`,
yesterday 00:00 to yesterday at the current time), so partial today compares with an
equally partial day. `month` is the calendar month to date; `projected_usd` =
`spent_usd` / elapsed days (fractional, at least a quarter day) × days in the month.

## Endpoints

- `GET /api/usage/series?period=&agent_id=&tz=` → `UsageSeries`
- `GET /api/usage/rank?period=&agent_id=&tz=` → `UsageRank` (agents and models, by cost
  then tokens; a model without a price has `cost_usd: null`)
- `GET /api/usage/export.csv?period=&agent_id=&tz=` → the series' points as CSV with a
  UTF-8 BOM: `date,cost_usd,tokens,requests` (`hour,...` for `day`, labelled
  `YYYY-MM-DD HH:00`), the hours not started left out
- `GET /api/usage/agents?days=&agent_id=` keeps its shape and adds `cost_usd` and
  `unpriced_requests` per agent and `cost_usd` per model (its token counts stay as
  recorded). With `bucket=day` (and optional `tz`) the period is the last `days` local
  days and `buckets` holds one `UsageDay` per day (the model page uses `days=7`).

Contracts: `lonora_contracts.usage` and `packages/contracts/src/usage.ts`. Aggregation:
`lonora_db.usage` groups rows in PostgreSQL by local hour, agent, provider and model and
prices each group; migration `0052_usage_cost` adds the `ln_usage (owner_id,
created_at)` index the window scans use. Tests: `tests/test_usage_dashboard.py`.
