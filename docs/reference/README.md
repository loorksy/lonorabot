# Reference studies (2026-11-26)

Read-only studies made to decide how Lonora works, at the owner's request («احتاج منك استعمال floorplan دائمن …
قم بنشاء خريطة بستعمال floorplan لي OpenMausBot و rakazo لكي تفهم طريقة العمل و الloop و الهارنس و باقي الامور المهمة»).
Nothing here is Lonora's code or behaviour; the decisions taken from them are in `docs/proposals/`.

## Floorplan maps

`floorplans/<repo>/floorplan/` holds a map in the floorplan plugin's format (`floorplan/architecture@1`,
https://github.com/haydenschmitty/floorplan): `architecture.json` (every code file of the repository assigned to a part,
flows and a tour) and `descriptions/*.json` (a name and a one-line description for the files read for the studies).

| Repository | Commit studied | Licence | Code files mapped | Files described |
|---|---|---|---|---|
| [OpenMausBot](https://github.com/milind-soni/OpenMausBot) | 140172d | Apache-2.0 | 8,307 of 8,310 | 426 |
| [Rakazo](https://github.com/elie222/rakazo) | 10973b5 | Apache-2.0 | 5,444 of 5,468 | 352 |

The plugin's own scripts were not run here (the sandbox refused third-party code); the maps were written to its schema
and checked with an equivalent assignment checker. Its viewer (`index.html`) can be built from them with the plugin.

## Studies

`studies/` holds one report per repository and topic (`<repo>-<topic>.md`: loop, auth, models, tools, proactive,
multiagent, memory, framework, ui, evals), the gap analyses against Lonora (`gap-<topic>.md`), the study of Lonora's
model providers (`lonora-providers.md`), the provider sign-in policy research (`policy-subscription-signin.md`), and the
studies of AiChart (`aichart-*.md`) and of Lonora's trading knowledge (`lonora-trading-knowledge.md`). Short code
quotes from the Apache-2.0 repositories are attributed by path and commit.

## Plans made from them

- `docs/proposals/roadmap-2026-11.md` (and `.ar.md`): the ranked roadmap, with the owner's decisions.
- `docs/proposals/trading-expertise.md`: trading expertise as model skills, with the owner's decisions.
- `docs/proposals/model-catalog-and-chatgpt-signin.md`: the fixed model list and Sign in with ChatGPT (Amendment 4).
