Superseded by VISION.md

# Capabilities you can see: trusted sources, MCP in one tap, feeds and Secret cards

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

Each row records its effect tier (`read`, or `write_nonfinancial` for an MCP server; for
a server also the pinned tools the server marked read-only at review), how it was added
(`default`, `operator`, `owner_ui` or `owner_card`), the agent whose card
the owner confirmed, when it was last used and, once removed, when and how. One active
row per source; a removed row stays as the record and can be restored. Only the owner's
session adds, removes or restores a row (`/trusted-sources`, or a card decision); no tool
does.

The migration makes today's trust visible: every owner gets `github.com` (Skill imports
always trusted all of GitHub; now the owner sees it and can remove it), and each saved
connection that the operator declared in `LONORA_MCP_DECLARATIONS` (read from the
migrating process's environment) gets an `mcp_server` row at the read tier with the
declared endpoint and schema hashes (declared tools are read-only). Such an `operator`
row is the declaration made visible, not owner trust: it authorizes a tool only while
the declaration stands, so removing a declaration still stops its tool. Capabilities then
shows the row as waiting for the owner's review; once the owner reviews the server (a
card or **Review and trust**) the row becomes the owner's own (`owner_card` or
`owner_ui`) and no longer depends on the declaration. An owner created later gets
`github.com` the first time the list is read. Running the seed again adds nothing.
The downgrade refuses while a source the owner (or an agent within the owner's
choices) added or removed exists, so a removed `github.com` never comes back trusted
on the re-upgrade; a refused downgrade changes nothing.

## MCP servers

A tool runs when its server is trusted and the exact tool is pinned, or when the
operator declared it. The order is:

1. An operator declaration (`LONORA_MCP_DECLARATIONS`) still authorizes exactly as before:
   the optional allow override. `LONORA_MCP_OWNER_TRUST=false` is the operator's deny
   override: owner trust then authorizes nothing and trust cards are refused.
2. Otherwise the connection's active `mcp_server` row, added or reviewed by the owner (an
   `operator` row only stands for its declaration), must pin today's endpoint and the
   tool's name. At the read tier the tool must also be one the server marked read-only
   (MCP `readOnlyHint: true`) when the owner reviewed it; otherwise the call is refused
   with `mcp_tool_needs_write_trust`. Both are checked before any secret is read or any
   network is used.
3. After discovery the advertised input schema must hash to the pinned one. If it does
   not, the call is blocked (`mcp_schema_changed`) and the server raises one re-review
   `trust_source` card with the server's current tools (system source, no model; the same
   change shown, or declined in the last week, raises no second card).
4. A tool that could trade or move money is never pinned, is listed as blocked on the
   card and is refused even if pinned some other way (`mcp_tool_financial_forbidden`).
   The check fails closed. It blocks a tool when its name holds a trading, payment,
   wallet, crypto-asset or ticker, transaction, betting or lending word (order,
   position, transfer, wallet, eth, usdc, tx, sign, bridge, swap, bet, cashout,
   currency, ...), or a money word that needs context (token, coin, tip, approve,
   spend, exchange, convert, ...) next to a sending verb or an amount field. It also
   blocks a tool whose title, description or annotation title says so ("place an order",
   "send 5 ETH", "broadcast a signed transaction", "place a bet"), and any tool whose
   input schema is shaped like a transfer: an amount, value, quantity, volume or lots
   field together with a recipient, to, address, wallet, IBAN or account field, or any
   private key, seed or mnemonic field. Broker trading shapes are blocked the same way:
   a broker platform or trading term in the name (MT4, MT5, MetaTrader, cTrader,
   MetaApi, broker exchanges, lot, hedge, stop loss, take profit), a trading term next
   to an acting verb (`open_long`, `go_short`, `modify_sl`, `set_exposure`), a broker
   named in the description ("Close an MT5 ticket"), and an input schema shaped like an
   order or a position change: an instrument (symbol, instrument, ticker, pair) with a
   size (lot, size, units, quantity, volume), or a ticket, deal, position or order with
   a stop or a target. Money moves only through Lonora's executor.
   A server that offers any blocked tool is trusted to read only: its card offers the
   read tier alone, the owner's route refuses the write tier
   (`trusted_source_write_blocked`), and no card proposes widening it. A trading-shaped
   tool is never pinned, so its own `readOnlyHint` cannot admit it to the read tier.
   The card and Capabilities say what is enforced: tools that look like they trade or
   move money are blocked, and money moves only through the owner's grants.
5. At the read tier a tool still marked read-only after discovery runs; a hint that
   dropped is refused (`mcp_tool_needs_write_trust`). A remote hint only narrows: a tool
   that becomes read-only later still needs the write tier, because its review said
   otherwise. A `write_nonfinancial` call stores an effect receipt keyed by the call, so
   a replayed call returns its recorded result and never sends twice. Uncertain calls are
   not resent (the existing `mcp_execute` classification).

Tool names must follow the MCP naming rule (`[A-Za-z0-9_./-]`, at most 128); other names
and unsupported schemas are left out of a review, so a card never shows remote text
beyond a plain tool name. Descriptions and annotations never grant anything.

The owner trusts a server in one of three ways, all owner-session only:

- the agent's `owner_action_propose(kind="trust_source", source_kind="mcp_server",
  connection_id=…)` card: the server reads the tools when the card is raised and the card
  pins exactly those. It lists the tools, the ones that may change something and the
  blocked ones. When every tool only reads, the card has one **Trust**. Otherwise the
  owner taps **Trust: read only** (just the reading tools run) or **Trust: non-financial
  writes** (the decision carries the tier). A server trusted for reading whose work
  later needs a writing tool (`needs_write_trust` in `mcp_tools`) gets one more card
  from the agent, where the owner can widen the tier;
- the card that follows a Secret card that connected an MCP server. The server reads
  the new server's tools with the address and token the owner typed, before the
  transaction; the transaction that saves the server also raises its trust card. When
  its tools cannot be read (unreachable, a missing or wrong token, a timeout) or none can
  be trusted, no card follows. The confirmation line says which, and the agent that
  asked is woken to check the server with `mcp_tools` and propose `trust_source` or
  explain the problem. Nothing waits for a card that never comes;
- «التكاملات» (`/app/integrations`): an MCP server's sheet previews the tools with a digest
  («مراجعة الأدوات»), and approving
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
declaration or entity is refused before parsing. So is any body that could hide one
from that byte check: a UTF-16 or UTF-32 body, a NUL byte, or a declared encoding that
does not write that markup as ASCII does (UTF-8, ASCII and single-byte encodings such
as windows-1256 still parse). Items are bounded, stripped of markup, keep only HTTPS
links, and are labelled untrusted evidence.

- `news_feed_read` (read-only) reads the subscribed feeds (all, or one) or one public
  feed URL once. Subscribed feeds are named by name and domain, never by URL (a feed URL
  may carry a token).
- `news_feed_subscribe` reads the feed once, then subscribes it silently inside a trusted
  feed domain, or raises one `trust_source` card (`feed_domain` with the feed) that trusts
  the domain and subscribes.
- A feed the owner adds in settings trusts its domain. Removing the last feed of a site
  also removes that site from the list (restorable there), so an agent asks again before
  subscribing it.

X/Twitter is read through web search, analysts' feeds or a trusted X MCP server. Lonora
never logs in or scrapes with the owner's account; an X API key can be added later.

Channels (Telegram, signed webhook) now deliver to an agent the owner picks by name
(`deliver_to_agent_id`); the server resolves that agent's conversation. The raw
conversation id field is gone from the form.

## Secret cards that connect

`owner_action_propose(kind="secret", target=…)` raises a Secret card (VISION.md 7.2,
10.3) that connects one thing. The agent gives the non-secret details it took from the
owner's words in chat, and the card shows them as facts. An address may carry a key, so
the owner types it into the card with the secret:

| Target | Details from chat | The card asks for | Saved as |
| --- | --- | --- | --- |
| `mcp_server` (`service="x"`: "Connect X") | `name` (none for X) | the server's address, and an access token (optional) | `MCP_<NAME>_URL`, `MCP_<NAME>_TOKEN` (workspace) |
| `brave_search` | `name` (optional) | the API key | `BRAVE_API_KEY` (workspace) |
| `news_feed`, `economic_calendar` | `name` | the address, which may carry a key | `FEED_<NAME>_URL`, `CALENDAR_<NAME>_URL` (workspace) |
| `broker` | `metaapi_account_id` | the MetaApi token | the broker scope, never the workspace |

The card shows the names its values are saved under. Saving it
(`POST /owner-actions/{id}/secret`) stores the values encrypted and creates the
connection in the same transaction:
- A saved name is made unique, and one card's names share their number
  (`MCP_DESK_2_URL` with `MCP_DESK_2_TOKEN`), so one connection's value never replaces
  another's. An agent's own card may not name a value a connection uses: it is refused
  when raised (`owner_action_not_needed_secret_name_in_use`), and a card raised earlier
  settles `expired` (`secret_name_in_use`) when the owner saves it, writing nothing.
- An address is checked as its reader checks it (https, port 443, a host whose labels
  can be looked up, no user name, password or fragment). A key or token is trimmed, and
  one with a character no HTTP header carries is refused
  (`owner_action_secret_value_unsendable`).
- A feed or calendar saved this way keeps its address in the store (`secret_id`) and
  only its host on the row (`domain`); the feed tool, the calendar and its watches read
  the address from the store, and only while it is on that host
  (`integration_source_changed` otherwise). An address an enabled feed or calendar
  already reads is that connection: nothing new is saved. A feed item whose link points
  back at the feed itself (only a fragment or a query) has no link, since the feed's
  address may carry a key.
- An MCP server saved this way keeps its address in the store too (`url_secret_id`) and
  its fingerprint on the row (`endpoint_sha256`), which the trust checks compare.
- Web search takes one key: a second Brave card saved later settles `expired`
  (`credential_already_configured`) and writes nothing.
- A broker's token is checked with MetaApi first, and the card settles inside the
  transaction that stores it and creates the connection.

The value never enters the card, the transcript, an event, model context or agent code:
agents see "configured". After an MCP server is connected, the trust card for its tools
follows; after anything else, and after any trust card, the agent that asked is woken
once (`owner_card` run, a fixed server prompt) to continue the work that needed it.
Removing a connection keeps its secrets: they are the owner's (VISION.md 7.2.4), and
`DELETE /secrets/{secret_id}` is the only route that deletes a stored secret (14.3.11).
Deleting a saved MCP server removes its trust row too (kept as the record).

## Capabilities

`GET /capabilities` and the agents' `capabilities_list` (read-only) report the same
thing: the trusted sources, the Skills agents installed or wrote with their origin, the
saved MCP servers with their trusted tools and tier, the integrations and feeds (domain
only), and the built-in capabilities with an honest state: `ready`, `not_connected` (one
card connects it) or `not_set_up` on this server (no browser service, no analysis host,
no chart renderer, no search service). Web shows it under Settings ← «التكاملات»
(`/app/integrations`: news domains with undo, RSS feeds, MCP servers and their review,
skills with their undo); Mobile under Settings, Capabilities. Each entry has its Undo: remove or restore a source,
revoke an installed Skill version, remove an integration, remove an MCP server's trust.
A server trusted for reading counts the tools that need non-financial writes. A Skill
version the owner undid shows as undone (it no longer loads) and offers no second
Undo; Undo is offered only for an installed or agent-written Skill with a version. On
Mobile a server whose tools are not trusted yet has **Review and trust** with the same
preview, and **Set up integrations on the web** opens the web settings.

## Verification

- `tests/test_trusted_sources.py`: financial classification and review (wallet, payment,
  betting and transfer-shaped tools), identifiers, card lifetimes and confirmation texts,
  feed parsing and entity refusal (UTF-16, UTF-32 and EBCDIC bodies too), a private
  address refused before any request. On PostgreSQL: a trusted server runs without a
  declaration; at the read tier a writing tool is refused before any call and a dropped
  read-only hint after discovery; a changed schema blocks and raises one review card; a
  financial tool is refused; a wallet server's send tools are blocked on the card and
  never sent; the deny override, removal and deleting the server end trust; a seeded
  operator entry stops with its declaration until the owner reviews it; connecting a
  server that cannot be read, or offers only money tools, says so and wakes the agent;
  the owner preview pins exactly what was shown; write-tier calls never send twice;
  Skills install silently inside the list and ask once outside it (without any workspace
  access), and Undo in Capabilities marks the version undone and it no longer loads;
  feeds, the Brave key and a feed whose address carries a key reach agents as configured
  and never as values, and removing a site's last feed makes an agent ask again.
- `tests/check_trusted_sources.py` (fresh database): the migration seed, idempotence and
  round trip; adding an MCP server in two taps with its address and token never leaving
  the server.
- `tests/test_secret_card.py`: the Secret card's own fields and its connecting cards (a
  broker's token in the broker scope with its connection; each MCP server's address and
  token under names of their own, kept when the server is removed; a name a connection
  uses never replaced; a stored address read only on its saved host).
- `tests/web/capabilities.test.ts`, `tests/web/secret-card.test.ts`; Playwright
  `capabilities` and `secret-card` on Web and Mobile, in Arabic and English (Skill Undo
  on both; on Mobile, review and trust of a server).

## Known limits

- The financial classifier is a word and shape list; it errs toward blocking (an order
  book reader, a sheet cell update with an address and a value). A blocked read tool can
  still be declared by the operator; the owner cannot unblock it.
- The read tier relies on the server's own read-only hint, pinned at review: it can keep
  a tool from running, never let one run that the review did not mark read-only.
- A trust card for an MCP server pins the tools it listed when it was raised; a server
  that changes before the owner taps is blocked at first use and asks again.
- Feeds are read on demand; feed watches that wake an agent arrive with the Wave 2 wake
  primitive.
- If an MCP server's tools cannot be read when its card is saved, the server stays
  saved and its agent is woken to check it; the trust card comes only once its tools
  can be read.
- An MCP server's token and address saved from a Secret card are workspace secrets:
  VISION.md 7.2.3 names exactly two destinations, workspace and broker. Any agent may use
  a workspace secret by name (7.2.4), so a workspace command given that secret can call
  the server directly, outside Lonora's tool pinning and its block on tools that move
  money. Lonora's broker accounts stay behind the execution door: their passwords and
  the MetaApi token are broker secrets, which never enter the workspace.
- No key rotation is built (nothing in 7.2 asks for it). To change a key, a token or an
  address, remove the connection, connect it again from a new Secret card, and trust its
  tools again.
- An operator declaration (`LONORA_MCP_DECLARATIONS`, `credential_scope: integration`)
  also covers a server whose token is a workspace secret from a Secret card: both are
  scopes an MCP connection may name; a broker or provider value never is.
- A feed subscribed with `news_feed_subscribe` and a feed saved from a Secret card are
  told apart by their address only when it is on the row: the same public address added
  both ways makes two feeds.
