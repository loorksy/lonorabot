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
| `known defect` | The step failed exactly the checks a `defects` entry names: a product defect in another worker's area, named with its owner. Fixing it makes the step pass, and the test then requires the entry to be removed. |
| `not exercised` | Live only. The model chose not to produce the event the step needs, for example it did not close. Which choice the model makes is not asserted. |
| `void` | Step 6. |

Each step starts from its own seeded state, not from the steps before it, so a step does not wait for the steps before it.

- **`needs` entries.** A `code` or `tool` entry turns ready by itself when that name is on the commit. A `pending` entry names a feature whose code name is not known yet; it is replaced by a `code` entry when its owner's PR names it.
- **`partial`.** A step that runs today on a stand-in names the stand-in in the report. It becomes `not written` once the features under `until` are on the commit, so the stand-in can never keep passing in place of the real step.

## What a step asserts

- **Plumbing is exact.** For example: one close in the journal, one send at the broker, no second send after the drop, and the journal row settled from broker evidence.
- **Judgment is checked, not chosen.** A step that depends on the model passes when the agent:
  - acted within its authority (no permission refusal);
  - did not ask (no owner-action card, no waiting for input, no question);
  - explained in one line.

## What the harness induces

- **A lost broker reply.** The fake terminal applies the close and then drops the connection before answering (`AcceptanceTerminal.lose_reply`).
- **A price move.** The harness moves the fake terminal's quote and hands it straight to the watch check that the market stream calls (`check_watches` with `price_update`). The stream's own health gate and store are not exercised.
- **Compressed time.** The brief step takes the time it runs at (`brief_tick(db, owner, now)`), and the harness calls it with the times the step needs:
  - step 5: yesterday's brief time and today's, in the owner's zone, with no weekly close between them;
  - step 7a: an evening before the next weekly close (`latest_close`), then the first brief time after it.

  Before each pass the harness runs the gateway's broker observation (`maintenance_account_recovery`), so the brief reads the broker as it is.
- **The product's own wakes:**
  - the watch check of the gateway (`check_watches`);
  - the routine step (`dispatch_routines`), with a one-shot routine due now;
  - the brief step (`brief_tick`), which also wakes each agent for its weekly report;
  - the reconciliation step (`reconcile_ambiguous`);
  - the queued runs, which go through `execute_run` as the worker does. That includes the wakes those runs cause: peer runs, and the follow-up that returns a peer's answer to its sender.
- **Scripted turns by wake.** A script key `agent` answers that agent's runs; `agent@trigger` answers only the runs that trigger started, for example `lonora_id@morning_brief`.

## Offline: the local gate of every PR and of the merged main

```
service postgresql start
export LONORA_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/accept_test
.venv/bin/python scripts/agent_eval/acceptance.py --offline            # every step, a table
.venv/bin/python scripts/agent_eval/acceptance.py --offline --steps 4c # one step
```

- **No model and no network.** Scripted model turns go through Lonora's real loop, the real tool handlers and the real MetaApi adapter, over the fake terminal of `scripts/agent_eval/broker.py`.
- **The database.** The URL names a disposable `*_test` database. The run migrates it as a template, copies it for each step, and drops every copy.
- **The full pytest run includes it:** `tests/test_acceptance_scenario.py` fails when a step whose feature is here fails. GitHub Actions do not run it; the local gate does.

## Live: a real model, run by the lead on the owner's server

```
export LONORA_DATABASE_URL=postgresql+asyncpg://<superuser>@127.0.0.1:5432/accept_live_test  # disposable, never production
read -rs LONORA_ACCEPT_PROVIDER_KEY && export LONORA_ACCEPT_PROVIDER_KEY                      # typed, not echoed
.venv/bin/python scripts/agent_eval/acceptance.py --live --model <provider>/<model> [--steps 4a,4c,5,7a]
unset LONORA_ACCEPT_PROVIDER_KEY
```

- **The database role.** It must be allowed to create and drop databases: the run copies its template with `CREATE DATABASE … TEMPLATE`.
- **What the run prints.** The step table, its checks and error codes. It prints no key, token, login or account id.

- The same steps run, with the product calling the model through its own router and provider adapter.
- **The provider key.** It is saved into the disposable template through the product's own credential route. Without `LONORA_ACCEPT_PROVIDER_KEY`, the template keeps the placeholder that a cloud session's network proxy replaces.
- **The broker is the fake terminal**, unless `--broker demo` is given.

## The MetaApi demo account (`--broker demo`), run by the lead on the owner's server

```
export LONORA_DATABASE_URL='postgresql+asyncpg://<createdb role>:<password>@127.0.0.1:5432/accept_demo_test'
export LONORA_ENCRYPTION_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= LONORA_BOOTSTRAP_TOKEN=accept-demo-only LONORA_COOKIE_SECURE=false LONORA_AUTH_RATE_LIMIT_PER_MINUTE=10000
.venv/bin/python scripts/agent_eval/acceptance.py --offline --broker demo --steps 1
```

- **What it does.** Step 1 against MetaApi itself:
  - the harness asks at hidden prompts for the demo account's login, server, master password and the MetaApi token;
  - the owner's chat message names the login and server, as 9.2 has the owner do;
  - the password and token are saved through the broker Secret card's own route;
  - the gateway's provisioning step creates and deploys the account through MetaApi. The harness repeats it until the card is connected or failed, for up to the product's own deploy and read deadlines plus two minutes (about 22 minutes);
  - Lonora is woken with the balance read from the broker.

  The template's own (fake) connection is switched off first, so nothing in the run reaches MetaApi with it.
- **What it leaves behind.** Nothing.
  - A connected account is removed by the product's own disconnect (9.3). A failed one is removed by the provisioning step's own cleanup, which the harness waits for. This happens even when a check or a run fails.
  - The harness then asks MetaApi itself, with the owner's token, whether any account for this login and server is left. It reports one that is, without its id. That includes an account that was already there before the run: the product reuses it and does not remove it, so the owner removes it at MetaApi.
- **What it prints.** The step table and its checks, and nothing else.
  - While the run goes, its standard output is discarded (the MetaApi SDK prints account ids) and logging is off.
  - It prints no login, server, password, token, account id or balance.
  - The values live in the run's memory and in its disposable database, which is dropped.
- **The model.** Use `--live` in place of `--offline` (with `LONORA_ACCEPT_PROVIDER_KEY`, as above) to have a real model hold the conversation.
- **Only step 1 runs on the demo account.** The trading steps need an agent that may trade the new account without asking (Full mode, W-AUTH); until then they run on the fake terminal.

## Today's state (this commit)

| Step | State | Note |
|---|---|---|
| 4a, the news agent tells the others | pass, partial | The speech is given in the news agent's routine; no calendar source is fed. The gold agent is Lonora under the template's signed grant. |
| 4c, a connection drop during a close | pass, partial | Fake terminal. The actor is Lonora under the template's signed grant (`bank.seed`), not the gold agent in Full: modes are not on main. |
| 1, connecting | pass, partial | W-BROKER's fake MetaApi provisioning API and fake terminal; the MetaApi demo account only with `--broker demo`. |
| 3, the strategy PDF | not written | The feature (owner methods from files, #116) is on main; the step's runner is not written yet. |
| 5, the morning brief | known defect, partial | One defect: the brief shows a position an agent opened as opened by the owner. It keys a position by its MetaApi account id and the journal's entries by the connection's id. It belongs to W-BRIEF, and the scenario file names it. Not asserted: the pending approval with its reason, which comes with Ask mode (W-AUTH); and the day's events, because the brief's facts carry none and no calendar source is fed. The brief Lonora posts is checked to be posted once; its words are the model's. The gold agent is Lonora under the template's grant. |
| 6 | void | Amendment 1. |
| 7a, the weekly reports | pass, partial | Each agent's results are its journaled operations only; the per-label statistics wait for W-LEDGER. What each agent learned and changed is the model's own words and is not asserted. The gold agent is Lonora under the template's grant. |
| Every other step | pending | Its feature is not on main. Run `--offline` for the exact list. |
