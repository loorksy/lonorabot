# Web research: provider search first, Lonora's own tools as fallback — specification

**Status: Proposed.** The owner asked how agents should search the internet. This is the answer: a hybrid, as the
leading agents do. It changes how research reaches the model; it changes no trading path.

---

## 1. Today (in the code)

| Tool | Backend | Where it runs |
|---|---|---|
| `web_search` | Self-hosted SearXNG; the owner's Brave integration when SearXNG is not configured (`packages/tools/src/lonora_tools/search.py`) | Gateway |
| `web_fetch` | One HTTPS GET, HTML reduced to text by a simple parser, 2 MB read limit, 24,000 characters returned | Gateway |
| `web_browse` | Isolated Playwright/Chromium service (`browser.py`, `browser_service.py`) | Browser container |
| News and calendar | `news_feed_subscribe`/`read`, `economic_calendar_read`, trusted sources | Gateway |

No model adapter uses a provider's built-in web search: `packages/adapters/src/lonora_adapters/models/anthropic.py`
calls `/messages`, and `openai.py` (through `openai_compatible.py`) calls `/chat/completions`, both without server
tools.

## 2. Findings

- **Quality.** A provider's built-in search (the model searches and reads inside one call, returning citations) is
  clearly better than SearXNG, which scrapes upstream engines that throttle data-centre addresses.
- **Cost (published prices, to re-check at build time).** Anthropic's web search tool: $10 per 1,000 searches plus
  tokens. OpenAI's Responses `web_search` tool: $10 per 1,000 calls plus content tokens. DeepSeek documents a
  server-side search tool (with thinking disabled) and standalone search and fetch endpoints. On the owner's own key
  (VISION §12), about 50 searches a day costs about $15 a month plus tokens.
- **Free search APIs are small quotas.** Brave removed its free tier in February 2026 (a monthly credit of about 1,000
  queries remains); Tavily, Exa, Jina and Firecrawl give roughly 1,000 requests or a few dollars a month.
- **GDELT DOC 2.0** is a free, keyless global news search over 65 languages (searchable in English), with a guideline
  of about one request every five seconds: the best free source for market news.
- **How leading agents do it.** Claude Code's web search is Anthropic's built-in tool; Codex uses OpenAI's; nanobot
  supports both provider-hosted search (`hosted_web_search_enabled` in `nanobot/providers/model_api.py`) and its own
  `web_search` with configurable backends. None relies on scraping search engines from a terminal.
- **Terminal scraping** (`curl`, command-line search clients) meets the same throttling as SearXNG at lower quality.
  The terminal is the right place for official data APIs (central banks, statistics offices) called by scripts, which
  already works.

## 3. Design

### R1 — Provider search as the first path
- The model adapters offer the provider's built-in search when the agent's current model supports it:
  - **Anthropic:** the `web_search` server tool in the `/messages` request.
  - **DeepSeek:** its server-side search tool, on requests with thinking disabled.
  - **OpenAI:** the Responses `web_search` tool. This needs a Responses API path in the OpenAI adapter (today it uses
    Chat Completions), so it comes after Anthropic and DeepSeek.
  - Z.ai and OpenRouter: added when their search features are verified against current documentation.
- **Provenance (VISION §6.10).** Search results return as distinct blocks. On any such block the adapter's caller
  marks the run with `mark_external_content` (`packages/tools/src/lonora_tools/provenance.py`), so taint rules apply
  exactly as for `web_fetch`; the content is evidence, never instructions or permission.
- **Citations.** The URLs, titles and retrieval times the provider returns are stored with the agent's message, so
  replies cite what was actually retrieved.
- **Usage.** Each search call is recorded in `ln_usage` and priced in `lonora_core.model_pricing`, shown on the usage
  page. No cap, budget or limit (the owner decisions recorded in `docs/usage-dashboard.md`).
- **Fallback.** When a run falls back to a model without built-in search (model fallback), or the provider reports
  search unavailable, the run is offered Lonora's own `web_search` (R2) in the same turn.

### R2 — Lonora's own `web_search` as the fallback (free)
- **SearXNG** stays, tuned: keep only the upstream engines that answer from the server (checked by a probe), pass a
  time range and the news category when asked for recent news, return each result's published date.
- **GDELT** as the news backend of `web_search` (category `news`), behind one shared limiter that respects its rate
  guideline.
- **Optional owner keys** (BYOK) for a paid backend, tried before SearXNG: Brave (existing), Tavily, or DeepSeek's
  search endpoint with the owner's DeepSeek key.

### R3 — Better page reading (`web_fetch`)
- Follow up to five redirects, re-validating every hop with `validate_public_url` (today any redirect fails).
- Extract the main content (headings, paragraphs, lists, tables, links) instead of all page text, then apply the
  character cap; return the final URL and `observed_at`.
- Read PDFs with `pypdf` (already a dependency): central-bank statements and reports.
- `web_browse` stays for pages that need JavaScript.

### R4 — Research method (the research skill)
`packages/agent-runtime/resources/skills/research/SKILL.md` gains: prefer primary sources (central banks, statistics
offices, regulators); read the source itself, not a snippet; give the publication date and time zone; say when a claim
rests on one source; separate facts from forecasts. These are research-quality rules; trading decisions stay the
agent's (VISION P1).

## 4. Decisions for the owner

| ID | Decision | Recommendation |
|---|---|---|
| W1 | Provider search on by default when the model supports it | Yes |
| W2 | Order of providers | Anthropic, DeepSeek, then OpenAI after its Responses path |
| W3 | GDELT as the news backend | Yes |
| W4 | Optional owner keys for paid backends | Brave (existing), Tavily, DeepSeek search |

## 5. Stages

| Stage | Content | Done when |
|---|---|---|
| S1 | R3 page reading | Redirects, main content and PDF covered by tests; SSRF tests still pass |
| S2 | R1 for Anthropic: server tool, provenance mark, citations, usage | A search in a run marks external content and appears with its price on the usage page |
| S3 | R2: SearXNG probe and freshness, GDELT news backend | News queries return dated results without SearXNG |
| S4 | R1 for DeepSeek | As S2 |
| S5 | OpenAI Responses path, then R1 for OpenAI | As S2 |
| S6 | R4 research skill | Skill tests updated |

## 6. Mandate check

Provider search is a public API feature used with the owner's key (VISION §12); Lonora stays the one engine (P4);
external content is marked and tainted (§6.10); usage is shown without caps (owner decisions in
`docs/usage-dashboard.md`). No change to any trading path.
