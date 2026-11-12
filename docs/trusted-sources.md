Superseded by VISION.md

# Capabilities you can see: trusted sources, MCP in one tap, feeds and credentials

Wave 1.5 slice W15-8 (corrections 21 and 22, owner decision D3). Agents add and use
Skills, MCP tools and news sources by themselves inside one trusted-sources list the
owner can see and undo. A new source outside the list joins it only when the owner's
typed message names it (VISION 10.3.2, lead decision Q21 (b): no card); a new account or
credential takes one card in the conversation. No source, tool or credential ever carries money
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
(`default`, `operator`, `owner_ui`, `owner_message` or, for rows from the retired trust
card, `owner_card`), the agent that added it on the owner's words, when it was last used
and, once removed, when and how. One active row per source; a removed row stays as the
record and can be restored. Only the owner's session removes or restores a row
(`/trusted-sources`); a tool adds one only on the owner's own words (below).

## Trust from the owner's words

`lonora_tools.source_trust` (migration `0132_trust_from_owner_words` adds `owner_message`
and retires the `trust_source` cards). A tool adds a source when the owner's typed
message the run answers names it: `owner_message_id` is set (an owner message or the
owner's steering; never a routine, peer or card wake, and never once the run read
content someone else wrote), and that message, or one the owner added while the run
worked, names the source. Otherwise the tool returns `trust_requires_owner_message`,
nothing is trusted, and the agent asks the owner to name it in chat. So the agent trusts
first, before reading anything from the source.

Naming is a strict, case-insensitive match of the identifier standing on its own: not
after a letter, digit, dot, `@`, `-` or `word/`, and not before a letter, digit, `-` or a
dot that continues the name. `evil-github.com`, `news.example.com` and
`example.com.evil.io` do not name `example.com`; `acme/tools-fork`, `acme/tools.js` and
`evil/acme/tools` do not name `acme/tools`; `https://example.com/rss` names
`example.com`. What each kind accepts:

- feed: the feed's domain (`www.` folded), as `news_feed_subscribe` reads it;
- GitHub: `owner/repository` (optionally `github.com/` before it, `.git` after it) trusts
  the repository; `github.com/owner` alone (not followed by a path) trusts the owner.
  The repository wins when both are named;
- MCP server: its saved name or its URL host. A name inside another saved server's
  longer name ("Notes" in "Notes Pro") counts for the longer one only.

This check is the anti-injection gate only (Q21 (b), VISION 10.3.2): the server reads no
intent. Whether the owner wants the source trusted is the agent's judgment of his words
(VISION 5.1: the model decides), and the tool descriptions say trust applies only when
the owner's own message names the source and asks for it.

`mcp_trust` takes `tier`: `read` (the default) or `write_nonfinancial`, which the agent
asks for only when the owner asks for the server to write. The same naming gate applies.
A server that offers a tool that can trade or move money is kept to the read tier
(`write_tier: blocked_moves_money`) and that tool is never pinned. Feeds and
repositories have no tier.

The migration makes today's trust visible: every owner gets `github.com` (Skill imports
always trusted all of GitHub; now the owner sees it and can remove it), and each saved
connection that the operator declared in `LONORA_MCP_DECLARATIONS` (read from the
migrating process's environment) gets an `mcp_server` row at the read tier with the
declared endpoint and schema hashes (declared tools are read-only). Such an `operator`
row is the declaration made visible, not owner trust: it authorizes a tool only while
the declaration stands, so removing a declaration still stops its tool. Capabilities then
shows the row as waiting for the owner's review; once the owner reviews the server (naming
it in chat, or **Review and trust**) the row becomes the owner's own (`owner_message` or
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
   override: owner trust then authorizes nothing and `mcp_trust` is refused.
2. Otherwise the connection's active `mcp_server` row, added or reviewed by the owner (an
   `operator` row only stands for its declaration), must pin today's endpoint and the
   tool's name. At the read tier the tool must also be one the server marked read-only
   (MCP `readOnlyHint: true`) when the owner reviewed it; otherwise the call is refused
   with `mcp_tool_needs_write_trust`. Both are checked before any secret is read or any
   network is used.
3. After discovery the advertised input schema must hash to the pinned one. If it does
   not, the call is blocked (`mcp_schema_changed`) until the owner trusts the server
   again (naming it in chat, or **Review and trust**).
4. A tool that could trade or move money is never pinned, is listed as blocked and
   is refused even if pinned some other way (`mcp_tool_financial_forbidden`).
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
   A server that offers any blocked tool is trusted to read only: `mcp_trust` trusts the
   read tier alone and the owner's route refuses the write tier
   (`trusted_source_write_blocked`). A trading-shaped
   tool is never pinned, so its own `readOnlyHint` cannot admit it to the read tier.
   Capabilities says what is enforced: tools that look like they trade or
   move money are blocked, and money moves only through the owner's grants.
5. At the read tier a tool still marked read-only after discovery runs; a hint that
   dropped is refused (`mcp_tool_needs_write_trust`). A remote hint only narrows: a tool
   that becomes read-only later still needs the write tier, because its review said
   otherwise. A `write_nonfinancial` call stores an effect receipt keyed by the call, so
   a replayed call returns its recorded result and never sends twice. Uncertain calls are
   not resent (the existing `mcp_execute` classification).

Tool names must follow the MCP naming rule (`[A-Za-z0-9_./-]`, at most 128); other names
and unsupported schemas are left out of a review, so the owner never sees remote text
beyond a plain tool name. Descriptions and annotations never grant anything.

A server is trusted in one of two ways:

- `mcp_trust(server=…)` in a run whose owner message names the server (its saved name or
  host, or the connection id with the owner's words naming it): the tool reads the tools
  the server advertises now and pins exactly those, at the tier it was given. It
  checks the owner's words before contacting the server. A server trusted for reading
  whose work later needs a writing tool (`needs_write_trust` in `mcp_tools`) is widened
  the same way (`tier=write_nonfinancial`), when the owner names it and asks it to write. After a `connect_credential`
  card connects a server, the agent that asked is woken and tells the owner to name it;
- «التكاملات» (`/app/integrations`), owner session only: an MCP server's sheet previews
  the tools with a digest («مراجعة الأدوات»), and approving re-reads the server and
  refuses with `mcp_tools_changed` if anything moved since.

## Skills

`skill_package_import` checks the repository against the list before it fetches
anything. Inside the list (github.com by default) the pinned commit installs as before,
and the agent may activate it; outside it the import goes on only when the owner's
message names the repository (or `github.com/<owner>`), which then joins the list;
otherwise it returns `trust_requires_owner_message` without fetching.
`skill_repository_inspect` trusts a repository the owner's message names before it reads
it (afterwards the run has read the repository, so the owner's message no longer counts)
and reports `source_trusted`. Instructions-only packages (no utilities) need no analysis host: their
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
  feed domain; outside one only when the owner's message names the domain, which then
  joins the list (`trust_requires_owner_message` otherwise, nothing subscribed).
- A feed the owner adds in settings trusts its domain. Removing the last feed of a site
  also removes that site from the list (restorable there), so an agent asks again before
  subscribing it.

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
or agent code: agents see "configured". The agent that asked is woken once (`owner_card`
run, a fixed server prompt) to continue the work that needed it; for an MCP server it
asks the owner to name the server in chat so its tools can be trusted. Deleting a saved MCP server removes its trust row too (kept as the record).

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
  betting and transfer-shaped tools), identifiers, the naming and writing rules,
  credential confirmation texts,
  feed parsing and entity refusal (UTF-16, UTF-32 and EBCDIC bodies too), a private
  address refused before any request. On PostgreSQL: a trusted server runs without a
  declaration; at the read tier a writing tool is refused before any call and a dropped
  read-only hint after discovery; a changed schema blocks until trusted again; a
  financial tool is refused; a wallet server's send tools are blocked and never sent;
  the deny override, removal and deleting the server end trust; a seeded operator entry
  stops with its declaration until the owner reviews it; for a feed, a repository and a
  server, the owner's message naming it trusts it (`owner_message`, no card), a run
  without it, one naming another source, or one that read third-party content first
  trusts nothing; the write tier only on the owner's words and never with a money tool;
  the owner preview pins exactly what was shown; write-tier calls never send twice;
  Skills install silently inside the list (without any workspace access), and Undo in Capabilities marks the version undone and it no longer loads;
  feeds and the Brave credential reach agents as configured and never as values, and
  removing a site's last feed makes an agent ask again.
- `tests/check_trusted_sources.py` (fresh database): the migration seed, idempotence and
  round trip; adding an MCP server from chat (one form, then the owner names it) with the
  token never leaving the server.
- `tests/check_trust_migration.py` (fresh database): `0132` settles and retires stored
  trust cards and keeps `owner_message` across a downgrade and upgrade.
- `tests/web/capabilities.test.ts`; Playwright `capabilities` on Web and Mobile, in Arabic
  and English (Skill Undo on both; on Mobile, review and trust of a server).

## Known limits

- The financial classifier is a word and shape list; it errs toward blocking (an order
  book reader, a sheet cell update with an address and a value). A blocked read tool can
  still be declared by the operator; the owner cannot unblock it.
- The read tier relies on the server's own read-only hint, pinned at review: it can keep
  a tool from running, never let one run that the review did not mark read-only.
- `mcp_trust` pins the tools the server advertises when it runs; a server that changes
  later is blocked at first use until the owner names it again.
- Intent, including a negation such as "don't trust example.com" (which still names
  example.com), is the agent's judgment of the owner's words, not a server rule; so is
  asking for the write tier. The owner removes a source in Capabilities with one tap.
- Feeds are read on demand; feed watches that wake an agent arrive with the Wave 2 wake
  primitive.
- If the secure form creates its record but the confirmation fails, the record stays and
  shows in Capabilities, where the owner can remove it.
