# Capabilities you can see: trusted sources, MCP in one tap, feeds and credentials

Wave 1.5 slice W15-8 (corrections 21 and 22, owner decision D3). Agents add and use
Skills, MCP tools and news sources by themselves inside one trusted-sources list the
owner can see and undo. A new source outside the list, or a new account or credential,
takes one card in the conversation. No source, tool or credential ever carries money
authority: money moves only through the one executor, inside the owner's grants.

## The trusted-sources list

`ln_trusted_sources` (migration `0042_trusted_sources`, `down_revision =
0041_supervision_grants`) holds one row per source and owner:

| Kind | Identifier | What it admits |
| --- | --- | --- |
| `github` | `github.com` | Skill imports from every public GitHub repository (the default) |
| `github_owner` | an owner, case-folded | Skill imports from that publisher's repositories |
| `github_repo` | `owner/repository`, case-folded | Skill imports from that repository |
| `mcp_server` | a saved connection's id | The tools the owner reviewed: the endpoint and each tool's input schema are pinned |
| `feed_domain` | a host name (`www.` folded) | News feed subscriptions on that site and its subdomains |

Each row records its effect tier (`read`, or `write_nonfinancial` for an MCP server), how
it was added (`default`, `operator`, `owner_ui` or `owner_card`), the agent whose card
the owner confirmed, when it was last used and, once removed, when and how. One active
row per source; a removed row stays as the record and can be restored. Only the owner's
session adds, removes or restores a row (`/trusted-sources`, or a card decision); no tool
does.

The migration makes today's trust visible: every owner gets `github.com` (Skill imports
always trusted all of GitHub; now the owner sees it and can remove it), and each saved
connection that the operator declared in `LONORA_MCP_DECLARATIONS` (read from the
migrating process's environment) gets an `mcp_server` row at the read tier with the
declared endpoint and schema hashes. An owner created later gets `github.com` the first
time the list is read. Running the seed again adds nothing.

## MCP servers

A tool runs when its server is trusted and the exact tool is pinned, or when the
operator declared it. The order is:

1. An operator declaration (`LONORA_MCP_DECLARATIONS`) still authorizes exactly as before:
   the optional allow override. `LONORA_MCP_OWNER_TRUST=false` is the operator's deny
   override: owner trust then authorizes nothing and trust cards are refused.
2. Otherwise the connection's active `mcp_server` row must pin today's endpoint and the
   tool's name. This is checked before any secret is read or any network is used.
3. After discovery the advertised input schema must hash to the pinned one. If it does
   not, the call is blocked (`mcp_schema_changed`) and the server raises one re-review
   `trust_source` card with the server's current tools (system source, no model; the same
   change shown, or declined in the last week, raises no second card).
4. A tool whose name or description says it can trade or move money (order, position,
   withdraw, transfer, wallet, broker, "place an order", "send funds", ...) is never
   pinned, is listed as blocked on the card and is refused even if pinned some other way
   (`mcp_tool_financial_forbidden`). Money moves only through Lonora's executor.
5. A `write_nonfinancial` call stores an effect receipt keyed by the call, so a replayed
   call returns its recorded result and never sends twice. Uncertain calls are not
   resent (the existing `mcp_execute` classification).

Tool names must follow the MCP naming rule (`[A-Za-z0-9_./-]`, at most 128); other names
and unsupported schemas are left out of a review, so a card never shows remote text
beyond a plain tool name. Descriptions and annotations never grant anything.

The owner trusts a server in one of three ways, all owner-session only:

- the agent's `owner_action_propose(kind="trust_source", source_kind="mcp_server",
  connection_id=…)` card: the server reads the tools when the card is raised and the card
  pins exactly those; the owner taps **Trust: read only** or **Trust: non-financial
  writes** (the decision carries the tier);
- the card that follows a `connect_credential` card for an MCP server (the server reads
  the new server's tools before the decision's transaction);
- Capabilities: **Review and trust** previews the tools with a digest, and trusting
  re-reads the server and refuses with `mcp_tools_changed` if anything moved since.

## Skills

`skill_package_import` checks the repository against the list before it fetches
anything. Inside the list (github.com by default) the pinned commit installs as before,
and the agent may activate it; outside it the tool raises one `trust_source` card
(`github_repo`) and returns `owner_trust_required` without fetching. When the owner taps
Trust the agent is woken once to continue. `skill_repository_inspect` reports
`source_trusted`. Instructions-only packages (no utilities) need no analysis host: their
files go to the agent's database-backed workspace store even when no workspace access is
configured. Packages with utilities still need sandbox validation before activation, and
the owner's revocation (Undo in Capabilities) is unchanged.

## News feeds (D3)

`news_feed` is an integration type: a public HTTPS RSS or Atom feed that every agent
reads. Reading goes through the SSRF-safe public client (`public_get`): HTTPS only, the
host resolved once and every address checked public, the connection pinned to that
address, at most three redirects each checked again, 2 MiB at most. A document type
declaration or entity is refused before parsing. Items are bounded, stripped of markup,
keep only HTTPS links, and are labelled untrusted evidence.

- `news_feed_read` (read-only) reads the subscribed feeds (all, or one) or one public
  feed URL once. Subscribed feeds are named by name and domain, never by URL (a feed URL
  may carry a token).
- `news_feed_subscribe` reads the feed once, then subscribes it silently inside a trusted
  feed domain, or raises one `trust_source` card (`feed_domain` with the feed) that trusts
  the domain and subscribes.
- A feed the owner adds in settings trusts its domain.

X/Twitter is read through web search, analysts' feeds or a trusted X MCP server. Lonora
never logs in or scrapes with the owner's account; an X API key can be added later.

Channels (Telegram, signed webhook) now deliver to an agent the owner picks by name
(`deliver_to_agent_id`); the server resolves that agent's conversation. The raw
conversation id field is gone from the form.

## Secure credential cards

`owner_action_propose(kind="connect_credential", target=…)` offers a form in the
conversation for `mcp_server` (`service="x"` titles it "Connect X"), `news_feed`,
`brave_search`, `economic_calendar` or `broker`. The client posts the value straight to
the owner API (`/integrations/secrets` then `/integrations` or `/mcp`, or
`/trading/connections` for a broker) and confirms the card with only what was created
(`connected: {resource, id}`); the server checks it is the card's kind of connection and
is configured. The value never enters the card, the transcript, an event, model context
or agent code: agents see "configured". After an MCP server is connected, the trust card
for its tools follows; after anything else, and after any trust card, the agent that
asked is woken once (`owner_card` run, a fixed server prompt) to continue the work that
needed it.

## Capabilities

`GET /capabilities` and the agents' `capabilities_list` (read-only) report the same
thing: the trusted sources, the Skills agents installed or wrote with their origin, the
saved MCP servers with their trusted tools and tier, the integrations and feeds (domain
only), and the built-in capabilities with an honest state: `ready`, `not_connected` (one
card connects it) or `not_set_up` on this server (no browser service, no analysis host,
no chart renderer, no search service). Web shows it under Settings, Capabilities; Mobile
under Settings, Capabilities. Each entry has its Undo: remove or restore a source,
revoke an installed Skill version, remove an integration, remove an MCP server's trust.

## Verification

- `tests/test_trusted_sources.py`: financial classification and review, identifiers,
  card lifetimes and confirmation texts, feed parsing and entity refusal, a private
  address refused before any request; on PostgreSQL a trusted server runs without a
  declaration, a changed schema blocks and raises one review card, a financial tool is
  refused, the deny override and removal end trust, the owner preview pins exactly what
  was shown, write-tier calls never send twice, Skills install silently inside the list
  and ask once outside it (without any workspace access), feeds and the Brave credential
  reach agents as configured and never as values.
- `tests/check_trusted_sources.py` (fresh database): the migration seed, idempotence and
  round trip; adding an MCP server from chat in two taps with the token never leaving the
  server.
- `tests/web/capabilities.test.ts`; Playwright `capabilities` on Web and Mobile, in Arabic
  and English.

## Known limits

- The financial classifier is a word list; it errs toward blocking. A blocked read tool
  can still be declared by the operator.
- A trust card for an MCP server pins the tools it listed when it was raised; a server
  that changes before the owner taps is blocked at first use and asks again.
- Feeds are read on demand; feed watches that wake an agent arrive with the Wave 2 wake
  primitive.
- If the secure form creates its record but the confirmation fails, the record stays and
  shows in Capabilities, where the owner can remove it.
