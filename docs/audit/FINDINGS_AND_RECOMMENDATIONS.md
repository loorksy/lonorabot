# Findings and recommendations

Baseline: `5315a8cc634486d54b1a64c1fd211b3e46429f14` · Audit date: 2026-10-27 · Source: this checkout.

[System](COMPLETE_SYSTEM_AUDIT.md) · [Capabilities](COMPLETE_CAPABILITY_INVENTORY.md) · [Traces](END_TO_END_EXECUTION_TRACES.md) · [Diagrams](ARCHITECTURE_DIAGRAMS.md) · [Findings](FINDINGS_AND_RECOMMENDATIONS.md) · [Coverage](AUDIT_COVERAGE_MANIFEST.md)


## Classification and confidence

Findings are bounded to the inspected baseline. A **confirmed defect** has a concrete contradiction/control-flow failure in source, sometimes additionally reproduced with local stand-ins. A **source-supported risk** has a plausible failure path but unverified triggering conditions or an unresolved intended contract. A **capability gap** means a normal execution path is missing a concrete integration. A **tradeoff** is deliberate bounded behavior, not automatically a defect. An **unverified concern** is a question requiring further evidence. There is no claim that the unreviewed source is defect-free.

Priorities are engineering triage, not numerical security scores: P1 high consequence or an important contract violation; P2 material reliability/integration/security work; P3 documentation/clarity; informational for intentional constraints. No production incident, unauthorized real trade or exploitable live service was demonstrated.

| ID | Priority | Classification | Finding | Verification |
|---|---|---|---|---|
| F-01 | P1 | Confirmed defect | Explicit-approved trade batch continues after an ambiguous result despite tool's stop contract | Actual function body with local DB/executor stand-ins; source comparison |
| F-02 | P2 | Confirmed defect | Webhook transport status overwrites delivery lifecycle status | Actual adapter/merge expressions with local transport stand-in |
| F-03 | P2 | Confirmed operational behavior; readiness-consumer risk | `/ready` can return HTTP success when Gateway reports not ready; Compose only tests DB/API health | Static route/deployment trace; no running HTTP probe |
| F-04 | P2 | Confirmed failure-path defect | Upload writes file before DB/reference acceptance with no rollback cleanup; generic delete leaves bytes | Source order and repository delete path |
| F-05 | P2 | Source-supported reliability risk | Outbound delivery cursor/receipt commit precedes send, with no retry/reconciliation in dispatcher | Transaction/call-order trace; process-crash test outstanding |
| F-06 | P2 | Confirmed integration gap | Incoming-call external device delivery is not wired in normal Gateway execution | Runtime call site and `delivery is None` branch; production call-site search |
| F-07 | P2 | Conditional security risk | Public URL validation and actual connection use separate DNS resolution | Source boundary; no exploit test |
| F-08 | P2 | Source-supported operational risk | Serial maintenance work can delay the heartbeat beyond readiness freshness | Loop and freshness contract; no latency measurement |
| F-09 | P2 | Conditional correctness risk / unresolved contract | Root cancellation only fences immediate child Runs | Query/lease/peer-depth trace; descendant DB test outstanding |
| F-10 | P3 | Confirmed documentation drift | Agent creation and mobile capability descriptions lag implementation | README versus concrete routes/client composition |
| F-11 | Informational | Conservative recovery tradeoff / capability limitation | Ambiguous modify/cancel operations lack automatic definitive reconciliation | Explicit adapter branch; no broker evidence exercise |

## F-01 — Approved multi-operation execution does not stop on uncertainty

**Original contract:** `trade_close_positions` explicitly says to stop after an uncertain result and reconcile before retrying (`packages/tools/src/lonora_tools/trade.py:504`). That rule is part of the pre-change registration presented to the model; this audit made no application changes.

**Actual path:** `close_positions` freezes the reviewed request list in an approval; after owner approval, `approved_execution` iterates `frozen` (`trade.py:164`), awaits `context.trading.execute` (`:193`), appends and stores the result (`:200`), and continues without inspecting `result.status`. After the loop it marks the approval `completed` (`:217`). In contrast, `account_authorized_execution` explicitly breaks unless the result is confirmed (`:260`).

**Impact:** if the first broker mutation may have happened but its outcome is unknown, subsequent requests in the same explicitly approved batch can still be attempted. The user can receive a completed batch card containing unresolved results. This violates the stated stop rule and creates different uncertainty semantics for two paths to the same executor. It does **not** prove that later requests were unapproved or that the ambiguous request succeeded; each executor call still performs its normal authorization/preflight checks.

**Supporting executor context:** a prior operation returns its own receipt by ID (`packages/trading/src/lonora_trading/execution.py:140`); this alone does not halt later, distinct operations. The unresolved-account operation check in `require_account_execution` belongs to standing-grant enforcement (`packages/trading/src/lonora_trading/account_authority.py:124`), which is not the explicit-approval path. Broker recovery configuration can separately block later sends, but the approved loop does not enforce the advertised rule itself.

**Local reproduction:** the actual AST-extracted `approved_execution` was run with a preexisting approved row and local session/executor stand-ins. The first returned `ambiguous`, the second `confirmed`. Observed calls were both operation IDs, and the approval ended `completed`. No DB/provider/account was accessed. The exact probe is retained in Appendix B.

**Minimum repair:** stop advancing the approved list at the first uncertain result and preserve unresolved/unattempted entries in the durable batch projection. Decide separately whether a definitive failed operation should also halt; the current standing-authority path does. Do not rewrite the tool description to conceal the mismatch. Re-entry must inspect the same operation identity, and cannot silently discard or relabel remaining reviewed requests.

**Required validation before claiming fixed:** multi-request approved batch with first ambiguous; cancellation/transport uncertainty; durable restart at each result write; reconciliation then deliberate continuation; first definitive failure policy; standing-grant parity. Use isolated PostgreSQL and explicit broker fixtures, with no real trade. No fix was implemented.

## F-02 — Webhook receipt stores HTTP number as lifecycle status

**Evidence:** `WebhookAdapter.send` returns `{"status": response.status_code}` (`packages/adapters/src/lonora_adapters/channels/webhook.py:27`). Dispatcher then computes `{"status": "confirmed", **result}` (`packages/gateway/src/lonora_gateway/event_dispatch.py:155`) and stores it (`:161`). Rightmost dictionary keys win.

**Impact:** even a successful HTTP 200 produces receipt status `200`, inconsistent with the dispatcher's submitted/confirmed/ambiguous lifecycle. This makes operational inspection and any consumers expecting lifecycle strings unreliable. The current skip check only tests receipt existence, so this finding does not claim that the type mismatch itself causes repeated sends.

**Verification:** actual adapter class with local non-network transport plus exact dispatcher assignment produced numeric `200`. The narrow result is independently observable without importing the missing backend environment. No remote endpoint was contacted.

**Adjacent concern:** the adapter rejects only `response.is_error` and disables redirects (`webhook.py:19`). Non-error responses are accepted without an explicit 2xx rule. Runtime dependency behavior for redirect responses was not exercised; a real HTTP client fixture should define the intended success policy before broadening the finding.

**Minimum repair:** keep transport code in a separate field (for example, `http_status`) and reserve `status` for the delivery lifecycle; validate the adapter result shape. Define accepted response classes explicitly. Add an isolated dispatch/adapter test proving the persisted receipt schema for success, redirect, failure and timeout. No application change was made.

## F-03 — Readiness does not fail HTTP status for a stopped Gateway

**Evidence:** `/ready` calls DB health and directly returns a dictionary with `gateway_health` (`apps/api/src/lonora_api/health.py:21`). Gateway health reports `ready=False` if no recent running/ready instance exists (`packages/gateway/src/lonora_gateway/health.py:10`). There is no route branch setting HTTP 503 for that condition. Production Compose probes `/health`, which tests only database connectivity, and defines no Gateway-specific healthcheck (`infra/compose/docker-compose.prod.yml:35`, `:42`).

**Impact:** a monitor or rollout gate relying solely on HTTP success can consider the system ready while no Gateway can claim work or attach voice sessions. The JSON body exposes the distinction, so a consumer that explicitly reads it can make the right decision. Source behavior is confirmed; no live readiness incident or endpoint run was observed.

**Minimum repair:** decide and document the readiness contract. If `/ready` is a readiness gate, return a non-ready status when required Gateway availability is false and align the deployment probe with it. Keep DB liveness distinct as appropriate. Verify healthy/no-worker/stale-heartbeat/draining cases, including status code and body. This is a contract clarification for operational consumers, not a proposal to add another service.

## F-04 — Artifact persistence has an unhandled filesystem/DB split

**Evidence:** upload writes bytes at `apps/api/src/lonora_api/routes/artifacts.py:35`, then enters the DB transaction and calls repository creation (`:36`). Ownership/thread/reference validation can still fail in `ResourceRepository.create` (`packages/db/src/lonora_db/transactions.py:136`). The upload handler has no compensating unlink for that failure. `ArtifactRepository` inherits the generic deletion path (`packages/db/src/lonora_db/artifacts.py:8`); generic delete removes the row and emits an event, without deleting filesystem content (`transactions.py:211`).

**Impact:** rejected upload or DB failure can leave unreferenced bytes. Repeated failures and deleted artifacts can accumulate disk usage. No disclosure exploit or exhausted real disk was demonstrated; authenticated ownership and confined-path checks still apply. The repository includes generated-artifact repair code, but no general cleanup guarantee is established by the inspected paths.

**Minimum repair:** validate references before allocating bytes, use a staged file/commit protocol with failure cleanup, and define explicit retention/garbage-collection semantics for deletion. Preserve any intentional retention contract. Verify DB rejection, transaction failure, interrupted upload and deletion with a temporary artifact root. No user artifact was created or removed in this audit.

## F-05 — Outbound channel delivery can be lost across a crash

**Evidence:** dispatcher advances integration event cursor (`packages/gateway/src/lonora_gateway/event_dispatch.py:95`), creates submitted receipts (`:142`) and exits the transaction before transport begins (`:144`). Any existing receipt suppresses a later attempt (`:140`). The post-send transaction stores confirmed/ambiguous result. Production source search found this `channel:` receipt producer/consumer in the dispatcher and no channel receipt reconciler.

**Failure window:** process dies after the first transaction commits but before a send, or after remote acceptance but before final receipt write. The committed cursor/existing receipt prevents normal redispatch, and uncertainty remains unresolved. Failed/ambiguous attempts are similarly not retried by this code.

**Impact:** an assistant answer or mandatory attention notification may never reach its channel. Conversely, blindly retrying could duplicate one that was actually delivered. This is a source-supported delivery tradeoff/risk, not proof that all channels should retry automatically or support exactly-once semantics.

**Minimum improvement:** make delivery guarantees explicit. Distinguish not-yet-attempted work from sent-but-uncertain work; reconcile using provider evidence/idempotency where supported, or surface unresolved delivery for operator/owner action. Keep retries within known provider guarantees. Validate crash points around both transactions and network admission. No delivery was sent during the audit.

## F-06 — External incoming-call push is disconnected

**Evidence:** normal Gateway attention loop calls `incoming_tick(self.db, service.owner_id)` (`packages/gateway/src/lonora_gateway/service.py:160`). Function parameter `delivery` defaults to `None` (`packages/voice/src/lonora_voice/incoming.py:287`); `if delivery is None: continue` prevents provider send (`:333`). Created call state is `provider_unconfigured` (`:239`). `IncomingDelivery` is a Protocol; the runtime call sites found do not supply an implementation. Tests inject providers, which does not establish production wiring.

**Actual supported subset:** consent/category/quiet-hours/device checks, durable ringing/expiry/cancellation, events and an in-app Web/native overlay are present. Provider acknowledgement, device presentation, owner acceptance and live session creation are different facts.

**Impact:** presence of the incoming-call UI can be mistaken for reliable background device notification. The resident Gateway cannot produce that external effect through its current call. This is a partial/disconnected capability, not evidence that ordinary owner-initiated WebRTC is absent.

**Minimum improvement:** accurately label provider-unconfigured state in user/operational expectations. If background delivery is required, provide a concrete delivery adapter and wire it into the existing call while retaining uncertainty/consent checks. If not required, document the in-app-only boundary. Verify real test-device acknowledgement/presentation separately from source fixtures. No provider integration was added.

## F-07 — DNS validation does not bind the subsequent connection

**Evidence:** `validate_public_url` resolves all addresses and rejects non-global values, then returns the original URL (`packages/security/src/lonora_security/network.py:9`). `WebhookAdapter.send` subsequently creates an ordinary httpx client and posts that URL (`packages/adapters/src/lonora_adapters/channels/webhook.py:16`). The validation result is not a pinned/verified destination connection.

**Risk conditions:** an actor controlling an allowed configurable hostname/DNS can potentially change its answer between the check and connection. HTTPS hostname/certificate checks, allowed port, DNS caching and network egress policies constrain exploitability; none were tested. This is not proof of arbitrary internal HTTP access. Owner-configured URLs and any model-facing fetch routes should be evaluated with their actual authorization boundary.

**Minimum improvement:** enforce destination policy at connection resolution time or use an egress boundary that independently blocks private destinations. Preserve TLS hostname verification. Test controlled DNS answer changes, redirects, IPv4/IPv6 and disallowed addresses without contacting internal/production services. The current pre-check is useful but not a complete check-to-connect guarantee.

## F-08 — Heartbeat freshness depends on serial maintenance latency

**Evidence:** `Gateway.maintenance_loop` writes heartbeat, then awaits scheduler/outcome/reconciliation/recovery work before its next sleep/iteration (`packages/gateway/src/lonora_gateway/service.py:77`). Readiness uses a 45-second heartbeat age (`packages/gateway/src/lonora_gateway/health.py:10`). Reconciliation can iterate up to 50 due operations with external broker evidence reads (`packages/trading/src/lonora_trading/reconciliation.py:25`).

**Impact:** slow broker/DB work can delay heartbeat and other maintenance even if the process and unrelated loops remain alive. Readiness may show stale Gateway; task wake/recovery ticks can lag. Whether this occurs at current workloads requires measurement. It is a source-supported scheduling risk, not an observed outage.

**Minimum improvement:** ensure heartbeat has a bounded independent cadence, and bound/budget maintenance work with measured duration/error visibility. Do not equate process heartbeat with every subsystem being healthy. Validate delayed reconciliation and scheduler work under local controlled latency, including shutdown.

## F-09 — Cancellation does not recursively fence all descendants

**Evidence:** `cancel_run` cancels the root and queries only `RunRow.parent_run_id == row.id` (`packages/db/src/lonora_db/cancellation.py:35`). It increments each immediate child's fence but does not recursively visit their children. Peer delegation supports deeper ancestry, while ordinary cancellation checkpoints validate the current Run's lease (`packages/agent-runtime/src/lonora_agent/collaboration/peer_messages.py:17`; `packages/agent-runtime/src/lonora_agent/cancellation.py:5`; `packages/db/src/lonora_db/runs.py:204`).

**Risk/uncertainty:** an already-created deeper peer job may continue after the user cancels its root if no separate policy later blocks it. This does not prove a financial authorization bypass: financial handlers have their own current grant/lineage gates. The intended user contract for cancelling a delegation tree has not been established from fully reviewed specifications/tests, so this is not labeled a proven violation of a tree-wide contract.

**Minimum next step:** define whether root cancellation means root/immediate children or all descendants; then exercise root → peer → peer with owned isolated DB fixtures and active leases. If tree-wide cancellation is intended, propagate fencing in a transaction/order that preserves lock safety, and ensure outcome projection cannot resurrect work. Do not silently strengthen/weaken the contract based only on this recommendation.

## F-10 — README understates creation requirements and native surfaces

**Evidence:** `README.md:31` says agent creation needs only name/avatar/color. Actual specialist creation requires account/symbol and broker verification (`apps/api/src/lonora_api/routes/agents.py:34`); mobile creation reflects that binding (`apps/mobile/app/new.tsx:1`). `README.md:45` groups voice/market/task/knowledge/connection capabilities under the full Web interface, while native composition mounts voice session/overlay and chart surfaces (`apps/mobile/app/_layout.tsx:12`) and includes native capability screens/components.

**Impact:** setup and capability expectations can be wrong. This finding does not claim native feature parity or real-device readiness; native code presence is narrower evidence than full operational support.

**Minimum repair:** distinguish automatic personal agent from broker-bound specialist creation; update platform capability descriptions with implementation/configuration/verification status. Keep actual native binary/device requirements. Existing README was intentionally not edited because this audit may only create the six requested artifacts.

## F-11 — Modification/cancellation ambiguity remains unresolved automatically

**Evidence:** MetaApi reconciliation explicitly returns ambiguous `mutation_evidence_required` for modify-order, modify-position and cancel-order actions (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:974`). Reconciliation maintenance only promotes definitive confirmed/failed results (`packages/trading/src/lonora_trading/reconciliation.py:25`).

**Tradeoff:** current target state can be compatible with several causes; without historical mutation evidence, inferring that a particular operation succeeded can be wrong. Preserving ambiguity is safer than declaring success or resending blindly.

**Operational limitation:** the operation can remain unresolved indefinitely under the available adapter logic; standing authority can block on unresolved account operations. Full operator resolution procedure was not established. Do not promise universal automatic recovery.

**Minimum improvement:** document supported recovery cases and needed evidence. Add definitive reconciliation only when broker-provided evidence can bind the exact operation. Treat an operator resolution path as a separate authenticated/audited contract, not a model override. No such mutation was performed or proposed as an automatic repair.

## Other observations, not confirmed defects

- The Web build warns about a 718.56 kB minified app chunk. No client timing/load benchmark was run; some routes already lazy-load. Optimize only against measured impact.
- Python package version ranges and installed-snapshot JS checks do not establish reproducible clean deployment. A clean-install/container gate would answer that; no dependency audit was run.
- TS/Python contract duplication, Web/native parallel code and JSON-state persistence create consistency work. The source request/catalog indexes are a starting point; no blanket incompatibility finding is justified.
- Generic helpers and thin wrapper packages may be unused by normal entry paths. Complete dynamic import/dead-code analysis is outstanding; do not delete them based on filename similarity.
- Broker-confirmed versus independently verified result is an intentional distinction. Pending verification is not automatically a failed transaction.
- The direct authenticated owner trade endpoint intentionally omits an agent lease. There is no finding that it bypasses the owner's authority.
- Strict CSP on HTML/SVG artifact previews is present. Inline preview alone is not proof of XSS.
- Client periodic/reconnect refresh exists. Missing a particular event does not prove permanently stale journal UI.

## Prioritized verification backlog

1. Fix F-01 through the existing execution/journal contract and validate isolated DB interruption/resume cases.
2. Repair F-02/F-04; specify F-05 recovery guarantees and test crash windows.
3. Verify readiness/heartbeat behavior with actual API/Gateway processes and controlled external latency.
4. Verify descendant cancellation, financial ancestry, authority revocation and exact plan/target changes under concurrent DB transactions.
5. Complete provider adapter/voice/device/MCP/workspace integration in synthetic/local test environments, then use authorized dedicated external test resources where required. Stand-ins never certify real execution.
6. Complete the outstanding `I`/`T` semantic scope in the coverage manifest, including executable CI code and migration transformations.

## Appendix A — Actual isolated Webhook/source and structural probe

This is the exact standard-library probe executed from scratch space. It parses sources, checks shell syntax/migration parent graph, reproduces the status overwrite with a local transport and confirms baseline hashes. Its helper paths refer to audit-session scratch inputs; the hash inventory is preserved in the coverage manifest for future reconstruction. It does not exercise HTTP or PostgreSQL.

```python
import ast, asyncio, hashlib, hmac, json, pathlib, subprocess, types
root=pathlib.Path('/home/vercel-sandbox/workspace/repos/github.com/loorksy/lonorabot')
index=json.load(open('/tmp/lonora-audit-index.json')); results={}
shell=[f['path'] for f in index['files'] if f['kind']=='shell']
for p in shell:subprocess.run(['bash','-n',str(root/p)],check=True,capture_output=True)
results['shell_syntax']={'files':len(shell),'passed':True}
revs={}
for p in sorted((root/'packages/db/migrations/versions').glob('*.py')):
 if p.name=='__init__.py':continue
 vals={}
 for n in ast.parse(p.read_text()).body:
  if isinstance(n,ast.Assign):
   for t in n.targets:
    if isinstance(t,ast.Name) and t.id in ('revision','down_revision'):vals[t.id]=ast.literal_eval(n.value)
  if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id in ('revision','down_revision'):vals[n.target.id]=ast.literal_eval(n.value)
 if vals:revs[vals['revision']]={'parent':vals['down_revision'],'path':str(p.relative_to(root))}
assert len(revs)==32
roots=[x for x,v in revs.items() if v['parent'] is None];heads=set(revs)-{v['parent'] for v in revs.values()};assert len(roots)==len(heads)==1
for rev in revs:
 seen=set();p=rev
 while p is not None:
  assert p in revs and p not in seen;seen.add(p);p=revs[p]['parent']
results['migration_graph']={'count':len(revs),'roots':roots,'heads':sorted(heads),'passed':True}
# Execute exactly the repository adapter class with local stand-ins; no dependency install or network.
p=root/'packages/adapters/src/lonora_adapters/channels/webhook.py';tree=ast.parse(p.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
class Response:
 status_code=200
 is_error=False
class Client:
 def __init__(self,**kwargs):pass
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
 async def post(self,*args,**kwargs):return Response()
async def validate(url):return url
ns={'hashlib':hashlib,'hmac':hmac,'json':json,'Any':object,'httpx':types.SimpleNamespace(AsyncClient=Client),'validate_public_url':validate,'LonoraError':RuntimeError}
exec(compile(ast.Module(body=[cls],type_ignores=[]),str(p),'exec'),ns)
async def probe():
 raw=await ns['WebhookAdapter']('synthetic-local-only').send('https://example.invalid/unused','probe')
 dispatcher=root/'packages/gateway/src/lonora_gateway/event_dispatch.py';tree=ast.parse(dispatcher.read_text());assign=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and n.lineno==155)
 merged={'result':raw};exec(compile(ast.Module(body=[assign],type_ignores=[]),str(dispatcher),'exec'),merged)
 assert merged['result']['status']==200
 return {'adapter_status':raw['status'],'stored_status':merged['result']['status'],'expected_lifecycle_status':'confirmed','defect_reproduced':True,'scope':'isolated source expression with local transport stand-in; no HTTP integration test'}
results['webhook_receipt_probe']=asyncio.run(probe())
changed=[f['path'] for f in index['files'] if hashlib.sha256((root/f['path']).read_bytes()).hexdigest()!=f['sha256']]
assert not changed
results['baseline_unchanged']={'tracked_files':len(index['files']),'passed':True}
pathlib.Path('/tmp/lonora-audit-check-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
```

## Appendix B — Actual isolated approved-batch probe

This is the exact executed function-body probe. Dependencies are deliberately local stand-ins. The observed result confirms loop advancement after uncertainty; real DB locking, broker behavior and external settlement are outside its scope.

```python
import ast, asyncio, datetime, json, pathlib, types
p=pathlib.Path('/home/vercel-sandbox/workspace/repos/github.com/loorksy/lonorabot/packages/tools/src/lonora_tools/trade.py')
fn=next(n for n in ast.parse(p.read_text()).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='approved_execution')
class Request:
 def __init__(self,key):self.operation_id=key
 @staticmethod
 def model_validate(value):return value
class Result:
 def __init__(self,status):self.status=status
 def model_dump(self,**kw):return {'status':self.status}
class Select:
 def where(self,*a):return self
 def with_for_update(self):return self
class RowType:id=None
class ContextManager:
 def __init__(self,value):self.value=value
 async def __aenter__(self):return self.value
 async def __aexit__(self,*args):pass
requests=[Request('synthetic-one'),Request('synthetic-two')]
row=types.SimpleNamespace(id='approval',owner_id='owner',run_id='run',agent_id='agent',status='approved',requests=requests,broker_snapshot={},results=[])
class Session:
 def begin(self):return ContextManager(self)
 async def get(self,*a,**kw):return row
 async def scalar(self,*a,**kw):return row
class Db:
 def sessions(self):return ContextManager(Session())
called=[]
class Trading:
 async def execute(self,owner,request,lease,authorization):
  await authorization();called.append(request.operation_id)
  return Result('ambiguous' if len(called)==1 else 'confirmed')
context=types.SimpleNamespace(db=Db(),lease=types.SimpleNamespace(run_id='run'),call_id='call',owner_id='owner',agent_id='agent',thread_id='thread',trading=Trading())
async def require_lease(*a,**kw):return types.SimpleNamespace(agent_id='agent',model_metadata={})
async def no_op(*a,**kw):pass
async def owned(*a,**kw):return types.SimpleNamespace(agent_id='agent',group_id=None)
async def snapshot(*a,**kw):return {}
async def interrupt(*a,**kw):return False
ns={'ToolContext':object,'TradeRequest':Request,'TradeResult':Result,'Any':object,'stable_id':lambda*a:'approval','require_lease':require_lease,'require_financial_agent':no_op,'TradeApprovalRow':RowType,'available_authority':no_op,'management_snapshot':snapshot,'owned_thread':owned,'LonoraError':RuntimeError,'user_interrupt_pending':interrupt,'trade_fingerprint':lambda r:r.operation_id,'utcnow':lambda:datetime.datetime.now(datetime.UTC),'approval_event':lambda*a:None,'select':lambda*a:Select()}
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(p),'exec'),ns)
result=asyncio.run(ns['approved_execution'](context,requests))
assert called==['synthetic-one','synthetic-two'];assert result['results'][0]['status']=='ambiguous'
output={'source_function':'approved_execution','called_operations':called,'statuses':[r['status'] for r in result['results']],'approval_terminal_state':row.status,'defect_reproduced':True,'scope':'actual function body with local database and executor stand-ins; no provider operation or DB integration'}
pathlib.Path('/tmp/lonora-audit-batch-probe.json').write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))
```

Observed output:

```json
{
  "source_function": "approved_execution",
  "called_operations": [
    "synthetic-one",
    "synthetic-two"
  ],
  "statuses": [
    "ambiguous",
    "confirmed"
  ],
  "approval_terminal_state": "completed",
  "defect_reproduced": true,
  "scope": "actual function body with local database and executor stand-ins; no provider operation or DB integration"
}
```
