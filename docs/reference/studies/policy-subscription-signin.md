# Subscription sign-in for third-party products (research date 2026-11-26)

Method note: Anthropic pages were fetched directly (verbatim quotes below). The sandbox could NOT reach
developers.openai.com, help.openai.com or openai.com (DNS/proxy 403), so every OpenAI statement comes from
web-search result summaries of OpenAI's own pages, not from a fetched page. Those are marked [SEARCH-SNIPPET, unverified verbatim].
Re-check them before building.

## 1. Anthropic

### Verdict
A hosted product sold to customers may NOT offer "Sign in with Claude" (Free/Pro/Max OAuth) or route calls through
subscription credentials, unless Anthropic previously approved it. No public approval or partner program was found;
the only route named is "contact sales". The supported paths are API keys (Console / Bedrock / Vertex / Foundry) or the
new beta "linked billing" (customer's own API-billed Console org, no key sharing, not a subscription).

### Primary quotes
1. Legal and compliance, https://code.claude.com/docs/en/legal-and-compliance (undated page, fetched 2026-11-26):
   - "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users."
   - "Moreover, developers may not collect, store, or intermediate Claude.ai credentials or session tokens — sign-in to a Claude account must complete through Anthropic's own flow."
   - "Developers building products or services that interact with Claude's capabilities, including those using the Agent SDK, should use API key authentication through Claude Console or a supported cloud provider."
   - "OAuth authentication is intended exclusively for purchasers of Claude Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications."
   - "Advertised usage limits for Pro, Max, and Ultra plans assume ordinary, individual usage of Claude Code and the Agent SDK."
   - "Anthropic reserves the right to take measures to enforce these restrictions and may do so without prior notice."
   - "For questions about permitted authentication methods for your use case, please contact sales."
   - Narrow allowed case, same page: it "does not prevent an end user from signing in to the unmodified Claude Code binary with their own Claude subscription, including where a platform hosts Claude Code".
   - Section "Can customers offer Claude Code in their products?": running Claude Code in hosted sandboxes requires the Commercial Terms; "The Claude Code binary must not be modified... customers may not remove, disable, or restrict any authentication method built into it (including methods that permit signing in with a Claude account...)"; "Customers may not pay for, resell, or intermediate Claude usage on their end users' behalf. Each end user must authenticate with their own Anthropic API key, Claude subscription plan credentials, or 3P inference provider credential."
   - Implication for a dedicated-server-per-customer assistant: only defensible if the product literally installs and runs the UNMODIFIED Claude Code binary on the customer's server and the customer logs in themselves (Anthropic's own flow, token never touched by the vendor). Calling the model from your own agent code with the subscription token is not covered.
2. Agent SDK overview, https://code.claude.com/docs/en/agent-sdk/overview (fetched 2026-11-26):
   - "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods described in the Quickstart instead."
   - "Use of the Claude Agent SDK is governed by Anthropic's Commercial Terms of Service, including when you use it to power products and services that you make available to your own customers and end users".
3. Consumer Terms, https://www.anthropic.com/legal/consumer-terms (effective Oct 8, 2025 per page):
   - "You may not share your Account login information, Anthropic API key, or Account credentials with anyone else."
   - "You also may not make your Account available to anyone else."
   - Prohibits access "through automated or non-human means, whether through a bot, script, or otherwise" and use to "resell the Services" (fragments as returned by the fetch tool; verify wording on the live page).
4. Support article, https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan (updates dated "June 15, 2026" and "October 7, 2026"):
   - "We've paused the previously-announced changes to Claude Agent SDK usage. For now, nothing has changed: Claude Agent SDK, claude -p, and third-party app usage still draw from your subscription limits."
   - "Claude Max, Ultra, and Team plans now include monthly API credits" covering "the Claude API, Claude Managed Agents, and the Claude Agent SDK and claude -p when you run them with an API key from your linked Claude Console organization."
   - Note: this describes a user's own local use; it does not grant third-party products permission.
5. Linked billing, https://claude.com/resources/articles/linked-billing-on-claude-platform (Nov 17, 2026, beta):
   - Third-party platforms (coding agents, workflow automation) let end customers "pay for Claude API usage without sharing an API key"; customer links their Claude Platform org (Owner/Admin/Billing role approves); platform "creat[es] an app in Console". Billed as API usage, not subscription. This is the official Anthropic-approved route for "customer brings their own Claude billing".
6. Claude Code authentication, https://code.claude.com/docs/en/authentication: `claude setup-token` makes a one-year `CLAUDE_CODE_OAUTH_TOKEN` "for CI pipelines and scripts" (model requests only). Technically works; the legal page above still forbids vendors collecting/intermediating it.

Not found: any public approval/partner program for subscription OAuth. "Unless previously approved" implies case-by-case via sales.

## 2. OpenAI

### Verdict
Official and new: "Sign in with ChatGPT" (SIWC) with "ChatGPT plan usage" (Go/Plus/Pro/Business per help center; one cookbook says Plus/Pro).
- Open-source and locally hosted apps: self-serve; no pre-issued client id (send client_id=dynamic_agent_client, OpenAI issues one), public client, no secret, no API key.
- Paid or remotely hosted commercial products: NOT self-serve. Limited trial for selected commercial partners; must submit the interest form (choose sign-in only vs sign-in plus plan usage). A hosted-per-customer assistant sold commercially is in this category: apply and wait for approval.
- Unofficial: reusing the Codex CLI's own OAuth client id / ~/.codex/auth.json tokens from a third-party backend. Not documented for that, can be blocked; official Codex app-server docs say app-server auth "has never been permitted for commercial or hosted services" (search summary).

### Findings [SEARCH-SNIPPET, not fetched from primary page]
- Launched as beta in July 2026 (identity only); expanded at DevDay (news dates conflict: Sept 29 vs 30, 2026) to plan usage. Secondary: thenewstack.io/sign-in-with-chatgpt, thestar.com.my 2026/10/04. Launch partners named by search: Airtable, GitLab, HubSpot, Notion, Supabase, Vercel (another source: Cognition Devin, T3, OpenClaw). Unconfirmed on primary.
- Docs: https://developers.openai.com/siwc (overview), /siwc/request-client-id ("currently offered to a select group of commercial partners"; waitlist = interest form), /siwc/quickstart, /siwc/website (website client ids start `oaiapp_`), /siwc/token-sharing-open-source (+ /sign-in, /profiles-and-sessions, /codex-app-server), cookbook https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt, full text https://developers.openai.com/siwc/llms-full.txt.
- Scopes: identity `openid profile email` (no access to conversations/API). Plan usage scopes: `offline_access resource.invoke chatgpt.tokens.use.direct`, user must authorize explicitly; registered scopes are a maximum; app should verify the plan-usage scope was granted before making AI requests.
- Users can set weekly per-app caps in ChatGPT settings; usage stops at the cap rather than falling back to the partner's billing. Business/Enterprise admins can restrict or disable third-party connections. (Secondary + help center via search.)
- Help center: https://help.openai.com/en/articles/20001410-sign-in-with-chatgpt , https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites (plan usage covers "open-source and locally hosted apps"; "paid or remotely hosted" -> interest form). Form: https://openai.com/form/sign-in-with-chatgpt-interest/
- Codex auth docs https://developers.openai.com/codex/auth (md: /codex/auth.md): "Sign in with ChatGPT" is for ChatGPT app, Codex CLI, IDE extension; tokens cached in ~/.codex/auth.json; CI/automation should use API key or access tokens (https://developers.openai.com/codex/enterprise/access-tokens, /codex/auth/ci-cd-auth).
- Codex App Server https://developers.openai.com/codex/app-server : login modes `apiKey`, managed `chatgpt` (Codex owns OAuth, device-code possible), and experimental `chatgptAuthTokens` (host app owns the token lifecycle, needs `experimentalApi`, refresh via `account/chatgptAuthTokens/refresh`). Search summary says docs state app-server authentication "has never been permitted for commercial or hosted services" and recommend migrating to SIWC. Open-source variant: https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server.
- Unofficial: community projects reuse the Codex CLI public client id (e.g. github.com/vec4me/openai-codex-auth, openai/codex PR #10012 context); a GitHub issue claims OpenAI publishes no way to register a third-party client id for the Codex backend; community says may be blocked. Not endorsed by OpenAI.
- Not confirmed: terms-of-use text on this subject; interest-form acceptance timeline; exact plan list (Go/Plus/Pro/Business vs Plus/Pro); whether a per-customer dedicated server counts as "locally hosted" (the customer's own machine) or "remotely hosted" (vendor-operated; almost certainly remote -> apply).

## 3. Practical conclusion for a vendor-hosted, per-customer-server assistant
- Anthropic: do not ship subscription sign-in without written approval from Anthropic sales. Ship API key entry, and evaluate linked billing (beta).
- OpenAI: ship API key; apply via the SIWC interest form for plan usage; meanwhile do not rely on the Codex client id. If the customer runs open-source/self-hosted software on their own machine, the self-serve open-source flow applies.

## URLs relied on
Fetched: https://code.claude.com/docs/en/legal-and-compliance ; https://code.claude.com/docs/en/agent-sdk/overview ; https://www.anthropic.com/legal/consumer-terms ; https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan ; https://claude.com/resources/articles/linked-billing-on-claude-platform ; https://code.claude.com/docs/en/authentication
Search-snippet only (host unreachable): the developers.openai.com, help.openai.com, openai.com URLs listed in section 2; secondary: https://thenewstack.io/sign-in-with-chatgpt/ , https://www.thestar.com.my/tech/tech-news/2026/10/04/openai-expands-chatgpt-with-apps-and-third-party-sign-in , github.com/openai/codex/pull/10012 , github.com/vec4me/openai-codex-auth
