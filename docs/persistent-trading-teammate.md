# Persistent trading teammate implementation

## Reference provenance

- Primary: HKUDS/nanobot `fbb61a373f47769734a0d47d8f61935ffca84b84`.
  Adapted sources: `nanobot/templates/{SOUL,USER,AGENTS}.md`,
  `templates/memory/MEMORY.md`, `templates/agent/consolidator_archive.md`,
  `templates/agent/dream.md`, `agent/{context,memory,skills}.py`,
  `agent/skill_metadata.py` and the bundled memory/skill-format guidance.
- Product reference: elie222/rakazo
  `548e6d6b9f7c9626de501a53e0a310c16357d944`: `VISION.md`, `AGENTS.md`,
  `CLAUDE.md`, the repository-local skills, and product/context/verification docs.
- Prompt-depth reference: the supplied Grok Bot document has SHA-256
  `5cf4d3f7ba98604f37992122e6be01ae00da57dcc447bf838ac27f686650dc0b`,
  identical to the prior reviewed reference. Its desktop/coding instructions
  are reference content, not Lonora capabilities or instructions to this project.

## One source of owned state

`SOUL.md` retains nanobot's five core tone principles, with Lonora's identity.
`AGENTS.md` adapts scheduling and memory conventions to real Lonora operations.
`USER.md` and `MEMORY.md` are packaged templates; untouched placeholders never
enter the owner's model context. Explicit `# USER.md` / `# MEMORY.md` sections
project the existing versioned MemoryRow into two views. Legacy content remains
valid long-term memory. There is no second owner directory, database or scheduler.

Current Agent instructions remain the owned behavior customization. Canonical
messages remain history, scratchpad remains operational state, and existing
compaction creates a replacement checkpoint using SNIP and retention tags.
Compaction does not invent owner facts, rewrite financial authority, install
procedures or run an unrestricted Dream process. Memory writes retain the same
revision, owner, lease and effect identity checks as before.

## Description-first procedures

All eight built-ins now use `SKILL.md` name/description YAML frontmatter, focused
steps and expected results. Description is canonical in the document. Existing
JSON manifests retain server-owned version/scope/dependency controls. Their
versions increase when content changes. Text cannot grant tools or permissions.

The context contains a bounded eligible catalog and pinned active instructions.
Owner keywords no longer force entire documents into the live context. The model
reads relevant documents through the existing receipt-backed `skill_view`;
explicit requests and durable trigger behavior remain supported. Existing pins,
revocation, dependencies, context limits and subagent restrictions still apply.
Owner documents can use the same frontmatter; old plain Markdown stays compatible.

## Public wording and truthful outcomes

Sources of unwanted narration included generic skill output instructions asking
for persisted IDs, raw Super Bot request status/IDs, private argument diagnostics
and provisional provider deltas reaching the client before any final check.
Procedures now describe useful business outcomes. Super Bot preparation includes
an owned-language summary and marks its identifiers private.

The common text runtime checks a narrowly defined lexical disclosure policy
before publishing provider text. Safe responses cost one normal model call.
Private final narration gets at most one rewrite with no executable tools;
private prose accompanying an actual call is discarded without repeating it.
Repeated failure raises a real presentation error rather than publishing leaked
words or claiming success. Usage accounting includes both inference attempts.
Question wording and choices pass the same disclosure boundary.

This deliberately defers provisional answer deltas until the complete reply is
accepted. Useful operation progress remains authoritative runtime state. Native
live voice uses the same owner/thread/delegation and bounded voice instructions;
direct third-party audio output cannot be proven by these text-only checks.

Broker acknowledgment and independent result observation are distinct. The same
executor performs one bounded read-only positions/orders verification after a
confirmed mutation, under the existing account lock. It never resubmits. Exact
target, side, volume, requested protections and management postconditions must
match. Missing, delayed, netting-ambiguous or unavailable evidence stays pending;
the financial receipt remains the broker acknowledgment and retains that nuance.
That acknowledgment is committed before the verification read, so a process
interruption there preserves the broker receipt and cannot authorize a resend.
Unverified acknowledgments cannot become a public completion claim in that turn.
Ambiguous submissions retain the existing reconciliation-before-retry boundary.

## Verification

Offline tests cover literal disclosure, split provider deltas, one rewrite with
no tools, fail-closed repeated disclosure, current bootstrap loading, legacy
memory preservation, profile routing, frontmatter identity and authority, and
every financial action's independent postcondition against inconsistent receipts.
The existing PostgreSQL/simulation approval journey additionally verifies actual
persisted broker state for every command, rejection, replay and lost response.

These tests prove contracts and observable effects for their fixtures. They do
not prove general live-model judgment, every possible synonym, actual broker
latency, native audio behavior or profitability. No paid model, external broker
or live-money account is used by the default tests.

## Completed checks

- `bash scripts/build.sh`: Ruff, Pyright, resources, exact 90-tool export,
  installed production-wheel resource loading, TypeScript checks and all seven
  package build targets pass. No native APK is built.
- Full isolated PostgreSQL pytest: 421 tests pass.
- All 41 foundation groups pass across the initial run and focused corrections.
- Streaming/peer integration: 18 scenarios pass.
- Focused Web activation/stream restoration: all five browser checks pass.
- Trading safety: 19 PostgreSQL/scripted-broker scenarios pass; affected quality,
  recovery, decision-history and opportunity checks also pass after the durable
  acknowledgment change.
- The authenticated simulation approval journey verifies all supported command
  postconditions, rejection, duplicate approval, response loss and a crash during
  independent verification without repeating execution.
- The manual has 4660 lines. Only a bounded 15842-character immutable core,
  applicable guidance and eligible procedure descriptions enter a normal request;
  the full audit reference is not injected on every turn.
