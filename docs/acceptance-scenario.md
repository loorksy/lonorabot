# The acceptance scenario (VISION.md section 16)

`scripts/agent_eval/acceptance.py` runs the mandate's acceptance scenario step by step. The steps are in `tests/fixtures/agent_eval/acceptance.json`. Each step:

- quotes section 16 to the letter;
- names the feature it needs and the worker who owns that feature;
- lists `needs`: the code that proves the feature is on this commit.

Step 6 (Stop) is void by Amendment 1.

## Step states

| State | Meaning |
|---|---|
| `pending` | The step's feature is not on this commit. The step is reported and not run. |
| `not written` | The feature is here, but the harness has no runner for the step yet. |
| `pass` / `fail` | The step ran on its own copy of the database. |
| `not exercised` | Live only. The model chose not to produce the event the step needs, for example it did not close. Which choice the model makes is not asserted. |
| `void` | Step 6. |

Each step starts from its own seeded state, not from the steps before it. A step therefore runs as soon as its own feature lands.

## What a step asserts

- **Plumbing is exact.** For example: one close in the journal, one send at the broker, no second send after the drop, and the journal row settled from broker evidence.
- **Judgment is checked, not chosen.** A step that depends on the model passes when the agent:
  - acted within its authority (no permission refusal);
  - did not ask (no owner-action card, no waiting for input, no question);
  - explained in one line.

## What the harness induces

- **A lost broker reply.** The fake terminal applies the close and then drops the connection before answering (`AcceptanceTerminal.lose_reply`).
- **A price move.**
- **The product's own wakes:**
  - the watch check of the gateway (`check_watches`);
  - the reconciliation step (`reconcile_ambiguous`);
  - the queued runs, which go through `execute_run` as the worker does.

## Offline: every PR and the merged main

```
service postgresql start
export LONORA_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/accept_test
.venv/bin/python scripts/agent_eval/acceptance.py --offline            # every step, a table
.venv/bin/python scripts/agent_eval/acceptance.py --offline --steps 4c # one step
```

- **No model and no network.** Scripted model turns go through Lonora's real loop, the real tool handlers and the real MetaApi adapter, over the fake terminal of `scripts/agent_eval/broker.py`.
- **The database.** The URL names a disposable `*_test` database. The run migrates it as a template, copies it for each step, and drops every copy.
- **The test suite runs it too:** `tests/test_acceptance_scenario.py`. It fails when a step whose feature is here fails.

## Live: a real model, run by the lead on the owner's server

```
export LONORA_DATABASE_URL=postgresql+asyncpg://.../accept_test   # disposable, never production
export LONORA_ACCEPT_PROVIDER_KEY=...                             # read from the environment, never printed
.venv/bin/python scripts/agent_eval/acceptance.py --live --model openai/gpt-5.4-mini [--steps 4c]
```

- The same steps run, with the product calling the model through its own router and provider adapter.
- **The provider key.** It is saved into the disposable template through the product's own credential route. Without `LONORA_ACCEPT_PROVIDER_KEY`, the template keeps the placeholder that a cloud session's network proxy replaces.
- **The broker is the fake terminal in both modes.** No run of this harness reaches MetaApi.

## Today's state (this commit)

| Step | State | Note |
|---|---|---|
| 4c, a connection drop during a close | runs | The actor is Lonora under the template's signed grant (`bank.seed`). It becomes the gold agent in Full once the modes are on main. |
| 6 | void | Amendment 1. |
| Every other step | pending | Its feature is not on main. Run `--offline` for the exact list. |
