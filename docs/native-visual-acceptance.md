# Native visual responses: release verification

Verified 2026-10-26. Runtime release:
`10dfdf7af72a4253762871ea07708623ac123c43`.
Implementation and limits: [native visual responses](native-visual-responses.md).
Later history-consolidation and documentation commits do not change this runtime.

## Delivered behavior

- The existing Agent chooses plain text, native components or mixed responses.
- A bounded, shared 26-component contract supports local calculations, controls,
  tables, diagrams, graphs, disclosures, tabs and authenticated resources.
- Web and native renderers share evaluation, design tokens and scoped local state.
- Existing message persistence, outbox, streaming, chart, voice and financial
  authorization paths remain in use. Generated controls cannot authorize trades.
- OpenUI's chat layout, composer and scroll behavior were adapted from actual
  source revision `9d73d17d2bbac565672a85e78f6eb7740cb0d9ca`; its MIT notice is retained.
- The Lonora Design Skill uses existing skill discovery. Stable visual guidance
  stays below 6,500 characters and does not add a presentation-model call.

## Checks

| Check | Result |
| --- | --- |
| Complete Python suite on migrated disposable PostgreSQL | 1,277 passed, 40.65s |
| `bash scripts/build.sh` | Passed; Python checks, policy/resources, lint, types and all 7 build targets |
| Shared evaluator, validation, streaming and scroll checks | 18 passed |
| Web generated-response browser cases | 5 passed; Arabic/English, light/dark, malformed fallback |
| OpenUI chat browser cases | 4 passed |
| Existing immediate-send and streaming browser regressions | 7 passed |
| Native components through Expo Web | 4 passed; Arabic/English, light/dark and reopened local state |
| Browser replay of final real-model observed response | 1 passed; displayed facts checked against compiled evidence |

The deterministic browser cases use fixtures for component coverage and real
authenticated application surfaces for interactions. They verify that local
changes do not send requests and follow-ups use the normal message endpoint.
They are separate from the actual-model evidence below. Counts are not additive
with focused reruns contained in the complete Python suite.

## Actual configured Agent

`scripts/verify_agent_journeys.py` ran through the installed Agent/runtime,
configured OpenAI `gpt-5.1`, real tool discovery, isolated physical workspace
files and persisted messages. No replacement model or mocked provider was used.

| Journey | Actual result | Time | Model generations |
| --- | --- | ---: | ---: |
| One-sentence definition | Plain text, no operation | 2.33s | 1 |
| Choose a useful file-size comparison | Agent chose plain text from inspected files | 10.60s | 3 |
| Requested observed comparison | Native metrics, table and graph; 13 verified facts | 16.09s | 4 |
| Architecture explanation | Native connected diagram | 10.46s | 1 |
| Educational sizing calculator | Native inputs and derived metric | 7.55s | 1 |

All five final journeys passed and removed their temporary identities, messages,
events and files. Broker services were denied and financial capability count was
zero. The six inspected files contained 2,245 real bytes in the isolated workspace;
these are test documents, not live account observations. Generation counts greater
than one are ordinary tool-loop rounds, not separate presentation calls.

Earlier trials exposed unknown observation identities, terminal delimiter errors
and malformed nested arithmetic. Corrections expose actual current-call IDs,
provide contract-tested compact examples, recover only terminal closers and retain
independently verified cells when another reference is missing. Interior syntax,
private/failed observations, unsupported actions and unauthorized resources still
fail validation. Malformed output keeps useful prose and a human-readable fallback.
These sample passes do not guarantee every future model composition or latency.

The final persisted observed response was replayed through the Web message
renderer, with displayed source metrics checked against its compiled facts.
Recorded response SHA256:
`753522b0fc217f3afcec7731c830657a8876fc269f1a082bac65e5ee4dc52ff6`.

## Publication and boundaries

- Exact API/Gateway/source release activated; health, readiness and `/app/` return
  200. Public Web assets match tested SHA256 values. Migration 0032 is installed.
- Public authenticated SSE became ready in 113.16ms in the final probe; this
  measures connection readiness, not model completion time.
- Signed Android OTA `1b910305-27f1-4715-b6c1-3ec060b36046` is active for existing
  APK 0.2.8 / versionCode 26102101 and native fingerprint
  `e4a51ffd7874ea0b8a4fc201e1c39ca376e826ca`. Public signature, every immutable asset,
  repeat-download and incompatible-runtime behavior were verified.
- No APK rebuild or signing change. No physical Android device acceptance was
  performed; Expo Web covers the native component implementation, not the device.
- No live broker order, position change or real-money trade was attempted. Existing
  stopped broker connections were not activated for this UI verification.
- No backup was created. Deployment staging and temporary remote evidence were
  removed after verification. Local diagnostic artifacts remain ignored by Git.

Detailed run logs are retained locally under `.runtime/native-rich-*`, including
the full suite, build, model journeys, server verification, browser replay and OTA
checks. They are excluded from the repository together with credentials/runtime data.
