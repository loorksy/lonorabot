# S19 local acceptance and release boundary

Branch: `feat/agent-operating-environment`; base `21293ad`.
Source ingestion/kickoff: `429205e`. Final code commits are recorded by Git rather than self-referential hashes in this document. No merge to main or production deployment is included. No migration required: scoped operational state belongs to existing Run checkpoints, Tasks, effect receipts, watch state and the existing event ledger.

## Executed acceptance

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Complete Python suite, isolated migrated PostgreSQL | 199 passed | `.runtime/s19-pytest-accepted.log`; includes voice tests and new recovery/chart units |
| Foundation acceptance runner | 26 isolated PostgreSQL fixtures +11 Task cases passed | `.runtime/s19-foundations-checked.log`; includes existing scope/skills/health/watch/execution/recovery/shadow/authority/attention and six new S19 integration fixtures |
| Safe-read recovery / normal AgentRuntime | Passed | `check_agent_environment.py`: global-router scripted errors, stable call identities, delayed claim, concurrent claim winner, new fences, schema repair, repeated-failure escape, oversized reads/effects, owner steering, worker death after unreceipted mutation, old ambiguous checkpoint fencing, identity-preserving financial reconciliation, actual bound market_candles + simulation broker recovery |
| Durable external wait/wake | Passed | `check_task_environment_wait.py`: real watch engine, timer, actual simulation broker reconciliation; same Task/Run, checkpoint/suspend crash gap, concurrent wake dedup and owner cancellation |
| Voice continuity | Passed | `check_voice_task_continuity.py`: final speech admission, partial financial speech no-op, silence/disconnect/reconnect, truthful Task inspection, revision and evidence-backed completion; no native/provider audio involved |
| Collaboration | Passed | `check_runtime_collaboration.py`: two actual concurrent peer runtimes, success/failure, duplicate outcome delivery, one active host and one synthesis; no financial authority transfer |
| Financial Goal call identity | Passed | `check_goal_call_identity.py`: freezes optional current-step intent; checkpoint replay returns the old decision instead of executing the next step |
| Memory provenance | Passed | `check_memory_provenance.py`: actual owner and Agent revision events; source Run/cursor; legacy unknown preserved |
| Bounded chart projection | 12 unit cases + existing PostgreSQL chart tools passed | Exact forex/metal/index/crypto names and multiple timeframes; aligned candle/indicator truncation; actual version/edit/snapshot compatibility |
| Ruff / formatting | Passed | Repository check,670 Python files formatted |
| Pyright | 0 errors | `.runtime/s19-final-types.log` |
| Client lint / types | Passed;7 workspace checks | `.runtime/s19-client-lint-accepted.log`, `.runtime/s19-client-types-accepted.log` |
| Web production build | Passed | `.runtime/s19-web-build.log`; existing non-fatal chunk-size advisory remains |
| Chromium Web acceptance | 24 passed | `.runtime/s19-web-tests.log`; actual API/DB/auth/chat/approvals/charts/authority/deletion |
| Expo Web acceptance | 8 passed | `.runtime/s19-mobile-tests.log`; actual API/DB/auth/native-client web render, not Android certification |
| Node client tests | 23 passed | `.runtime/s19-node.log`; voice transport/readiness, timeline, mentions and OTA checker |
| Skill manifest/tool resource validation | Passed | Existing packaged-resource validator against actual ToolRegistry |

Initial full-suite failure was a context-builder unit double without an operational-history query stub; its unrelated history collaborator was updated and the complete199-case PostgreSQL suite then passed. No application assertion was disabled. The later financial declaration/origin regression cases brought the final suite to199 cases. Test databases are disposable and every foundation fixture runs in its own migrated database. Scripted models and simulation/fake broker responses are explicit test inputs; no automated live/demo financial mutation or real provider speech was performed.

## Source audit / architecture review

Nanobot was read at `faf1efaf09d2d69d1887b6ac6b0c6441e3ccccb2`;36 mechanism dispositions and real execution paths are in `NANOBOT_ARCHITECTURE_STUDY.md`. Its source was not copied. Existing Lonora fencing, journal, global router, context governance, Tasks, voice and collaboration remain the single owners. Context observations carry timestamps/provenance and cannot rewrite authority. No hidden chain-of-thought is persisted.

Important deliberate boundaries:

- Recovery metadata describes an observation; it never enables Trading, removes Emergency Stop, expands exact scope, approves a card or signs Super Bot authority.
- Safe reads have at most two automatic retries. An equivalent failed route retains its budget across process/worker replacement and model call-ID changes.
- An interrupted unreceipted mutation is uncertain. It does not execute again merely because the worker restarted. Receipt-backed handlers reuse their existing stable operation identity and reconciliation.
- A context-size omission retains committed operation status/IDs; it is not fabricated effect failure.
- Owner revisions/cancellation and source/wake receipts prevent stale continuation. The same Task survives a call ending; speech cancellation is not financial cancellation.
- Tool-observed operational history is bounded to five relevant recent facts, with contract-hash matching and source event/Run/time. Owner knowledge, inferred Agent revision text and legacy unknown authorship are not silently conflated.
- The full01–18 feature program remains partial. S19 strengthens its shared operating environment; it does not claim all advanced domain requirements are delivered.

## External acceptance still open

`BLOCKED_EXTERNAL_NATIVE_ANDROID`: the owner explicitly prohibited building the application. No new APK, native build/export, installation, Samsung microphone/WebRTC/reconnect/permission verification or APK publication occurred. Expo Web and backend sideband tests cannot establish native device behavior. This is why S19's final completion/native gate rows remain blocked rather than claiming full completion.

Real provider/broker deployment acceptance is not performed by this branch: no production deployment/migration or owner goal/authority activation was authorized by specification19. All new external broker mutations remain behind existing approvals/global controls and are tested with simulation. No remote GitHub Actions pass is claimed; prior account billing failures are not local code validation.

A PostgreSQL server-process restart was not injected; worker interruption, expired lease/new fence, checkpoint recovery, duplicate events and ambiguous effects were exercised against real PostgreSQL. Running processes were not called native certification. Native tests may resume only after the owner permits the necessary device/build workflow.

Committed capabilities: `64fee8c` integrates backend/tools/context/recovery/receipts and behavioral tests; `ec60d97` connects authoritative wait state to existing client status. The initial source commit is `429205e`. Legacy checkpoint acceptance was rerun after the final policy change in `.runtime/s19-environment-confirmed.log`; final static checks use `.runtime/s19-final-types.log`.
