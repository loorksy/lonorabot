# The mobile shell under P5

Mandate P5: outside conversations the app has only the agent and conversation list, the
"needs your attention" view (11.7), the "What I know about you" view (8.4), the "What is
running" view (7.1.5) and sign-in. Everything else is done from chat. (The Stop control is
void by owner amendment 1.)

This file lists every mobile route (`apps/mobile/app`) and where it stands. A screen outside
conversations is removed in the change that shows its chat path works; until then it stays
here with what its chat path is missing.

## Allowed outside conversations

| Route | View |
|---|---|
| `(tabs)/index.tsx`, `archived.tsx`, `agents.tsx` | the agent and conversation list |
| `(tabs)/updates.tsx` | needs your attention (11.7) |
| `owner.tsx` | What I know about you (8.4) |
| `(settings)/running.tsx` | What is running (7.1.5) |
| `sign-in.tsx`, `server.tsx` | sign-in and its server address |

## Inside a conversation

`thread.tsx`, `group-thread.tsx`, `artifact.tsx`, `image.tsx`, and the screens opened from a
conversation's menu: `artifacts.tsx`, `routine.tsx`, `group-settings.tsx`, `skills.tsx`,
`bot-settings.tsx`.

`bot-settings.tsx`, with `components/account-authority-settings.tsx` and
`components/supervision-settings.tsx`, is named in 14.1.4: its removed features are another
worker's removal.

## Removed (the chat path works)

| Route | Chat path |
|---|---|
| `new.tsx` (create an agent from a template) | `agent_create` (`packages/tools/src/lonora_tools/agents.py`): the same service as `POST /agents/create`; without the owner's message it becomes a card |
| `(settings)/models.tsx` (models and providers, read-only) | `model_list` and `model_request` (`packages/tools/src/lonora_tools/models.py`) |

## Kept, tracked: outside conversations with no complete chat path

| Route | What the owner does there | Missing from the chat path |
|---|---|---|
| `(tabs)/tasks.tsx` | the agents' runs; a tap opens the report | reading works (`task_inspect`, `agent_inspect`, `runtime_status`); the generated-interface route `tasks` (`UI_ROUTES` in `packages/contracts`) still opens this screen, so it goes with that route |
| `charts.tsx` | the market chart workspace | `chart_open` and the chat's chart sheet work; the sheet imports `ChartWorkspace` from this route and the generated-interface route `market` opens it, so it goes with that route |
| `new-group.tsx` | create a group | no tool creates a group |
| `(settings)/integrations.tsx` | capabilities, trusted MCP servers and sources, skill revocations, delete an integration | no tool revokes or restores a trusted source or deletes an integration |
| `(settings)/voice.tsx` | voice status, reach-me, ringing device, quiet hours, reply language | `owner_preferences_update` sets reach-me, reply language and quiet hours; nothing chooses the ringing device or reads the voice transport status |
| `(settings)/account.tsx` | email, server, app language, usage, sign-out | usage works (`usage_read`); the app language and sign-out are device actions with no chat path |
| `(tabs)/settings.tsx` | the hub: the theme and the way to the screens above | the theme is a device setting; it is also the only way to «ما أعرفه عنك» and «ما الذي يعمل», which need another entry before the hub goes |
