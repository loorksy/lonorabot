# Owner CLI and terminal app, in the style of nanobot — specification

**Status: Proposed.** Needs the owner's go-ahead. It adds a third client next to web and mobile; it changes no agent
behaviour and stays within VISION P5 (chat is the control surface).

---

## 1. What exists today

| Program | Where it runs | Who uses it | What it does | State |
|---|---|---|---|---|
| `lonora` (server) — `infra/compose/lonora` | The server | Whoever operates the installation | status, start, update with automatic rollback, backup, restore, restore-test, logs, maintenance | Complete |
| `lonora` (workspace) — `packages/cli/lonora`, served by `apps/api/src/lonora_api/cli/app.py` | Inside the agents' workspace | Agents' scripts | `price`, `candles`, `account`, `positions`, `orders`, `wake`, `notify` | **Incomplete:** VISION §7.3's `trade`, `close`, `modify`, `cancel` are not built |
| — | The owner's own computer | The owner | Talk to Lonora and the agents from a terminal | **Does not exist** |

nanobot, for comparison (from its floorplan): `nanobot agent` (chat in the terminal), a native terminal app (`tui/`,
built on `@opentui`, with composer, command menu, `@` mentions, skills and sessions menus, diff and usage panels),
`onboard`, `status`, `channels login`, `provider login`, `plugins enable|disable`, `webui`, `update`, `remote pair`, and
slash commands (`/new`, `/stop`, `/compact`, `/model`, …).

This specification adds the missing third row and lists the completion of the second (§9).

---

## 2. Goal

The owner runs `lonora` on their own computer and gets Lonora in the terminal: the agent list, live conversations, the
fixed cards, the attention and "what is running" views — the same app as web and mobile, through the same API, plus
scriptable commands with `--json`.

---

## 3. Commands

**Interactive (`lonora` with no arguments opens the terminal app):**
- Left: Lonora, team agents and groups, each with its one status line (VISION §17). Right: the conversation, streaming
  live with run status, attachments, generated interface.
- Composer: multi-line, `@agent` mentions, attach files and clipboard images, queued messages while a run works.
- Slash commands map to allowed views only (P5): `/agents`, `/attention` ("needs your attention"), `/running` ("what is
  running", stop one or all), `/know` ("what I know about you"), `/switch @agent`, `/open` (this conversation in the web
  app), `/help`, `/quit`. Everything else is said in chat ("make a gold agent", "use model X for @euro").
- **Fixed cards rendered natively and faithfully** (VISION §10.3): Trade Approval (shows exactly what is approved;
  approve/decline), Mandate card, Secret card (masked input, never echoed, never in scrollback or shell history),
  operation settlement. A generated element can never stand in for a fixed card (§6.10).
- Generated interface (GenUI v2): supported components drawn as text (tables, metrics, lists, short charts); anything
  else shows a summary and an "open in web" link.

**Scriptable:**
```
lonora login <server-url>          browser approval, session stored in the OS keychain
lonora logout | whoami | status    status = the server's /ready and version
lonora agents [--json]
lonora send @agent "text" [--wait] [--json]
lonora tail @agent [--json]        follow a conversation
lonora attention [--json]
lonora running [--json] ; lonora running stop <process>
lonora open [@agent]
```
Human text by default; `--json` is an explicit scripting mode (normal views show no raw ids or JSON, VISION §17).
**Approvals are interactive only** (a terminal with the card on screen), decision C3.

---

## 4. Signing in

- New grant (decision C2): `lonora login https://<server>` asks the server for a short code, opens the browser at the
  server's approval page, the signed-in owner approves (with a passkey when device trust is enrolled,
  `apps/api/src/lonora_api/routes/device_authority.py`), and the CLI receives a native session like the mobile app's
  (`POST /mobile/login` sessions: revocable, listed with the owner's devices).
- Stored in the OS keychain (macOS Keychain, Secret Service, Windows Credential Manager); a plain file only with
  `--insecure-store`.
- Works the same for self-hosted servers and Lonora Cloud (`https://<handle>.lonora.app`).

---

## 5. Owner authority from a terminal

- Messages typed in the interactive app are the owner's typed messages, like web and mobile.
- **Messages sent by `lonora send` from a script are marked as scripted** and never count as "the owner's typed
  message" for trust grants (`trust_source`), ticket-ownership exceptions (§3.3.4) or reach-me settings (§8.2), unless
  the owner confirms them interactively (decision C4). A script that pipes text from a file must not be able to grant
  authority.

---

## 6. Transport and technology

- The existing REST API and the event stream (`/api/events/stream`), the same calls as the web app; types from
  `packages/contracts` (TypeScript).
- Recommended (decision C1): **TypeScript on Bun with `@opentui/core`**, as nanobot's terminal app, so the contracts are
  shared with web and mobile; single binaries per platform with `bun build --compile`, also published as an npm
  package.
- Charts: terminal graphics protocols where the terminal supports them, otherwise a link.

---

## 7. Arabic and right-to-left in a terminal

Arabic comes first (VISION §17), but terminals differ in bidirectional text and Arabic shaping. The app applies the
Unicode bidirectional algorithm to every displayed line and relies on the terminal's font for shaping; a test matrix
(iTerm2, Kitty, WezTerm, Windows Terminal, GNOME Terminal) is part of acceptance; `--lang en` and the owner profile's
language choose the interface language.

---

## 8. Naming

The command is `lonora` on the owner's computer. On a server where `/usr/local/bin/lonora` already belongs to the
operator CLI, it installs as `lonora-chat`, the same pattern the operator CLI uses for a second installation
(`lonora-<project>`).

---

## 9. Completing the workspace CLI (prerequisite)

Build the order commands of VISION §7.3 (`trade`, `close`, `modify`, `cancel`): through the execution door, journaled
and verified, `--key` idempotency, exit codes 0/10/20/30/77, a Trade Approval card when the calling agent is in Ask.
This finishes VISION phase 4 and is stage E0 of `docs/proposals/crypto-door-adapter.md` and gap G4 of
`docs/proposals/agent-environment.md`.

---

## 10. Delivery stages

| Stage | Content | Done when |
|---|---|---|
| C0 | Login grant and native session for the CLI; revocation | Session listed and revocable from web |
| C1 | Read-only: `agents`, `attention`, `running`, `tail` | Same data as web, Arabic and English |
| C2 | `send`, streaming conversation, attachments | A run's progress and result appear live |
| C3 | Fixed cards in the interactive app | Approval, mandate, secret and settlement flows pass the same tests as web |
| C4 | Terminal app polish: mentions, queue, generated-interface rendering, RTL matrix | Acceptance on the five terminals |
| C5 | Distribution: binaries, npm package, install guide | Install and login in under two minutes |

---

## 11. Decisions for the owner

| ID | Decision | Recommendation |
|---|---|---|
| C1 | Technology | TypeScript + Bun + `@opentui/core`, as nanobot |
| C2 | Login | Browser approval grant with native session |
| C3 | Approvals from scripts | Not allowed; interactive only |
| C4 | Scripted messages and owner authority | Marked as scripted; never grant authority without interactive confirmation |
