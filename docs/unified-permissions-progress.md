# Unified Agent Permissions — implementation record

Mandate: `lonora-specs/prompt4.md` (verbatim).

The feature is in progress on `feature/unified-agent-permissions`. No merge,
deployment, live financial operation or permission change has been performed.

## Inspected integration boundaries

- Existing AccountAuthority v2 supports full management with optional limits;
  bounded grants also allow execution without per-operation approval. Neither
  management_mode nor the presence of limits represents the supervised level.
- `AccountAuthorityProposal` already owns all ten actions, six optional numeric
  limits, selected/account scope, expiry and manual-position coverage.
- Device challenge and verification bind the exact envelope hash. Activation
  starts an existing continuous Task; revocation stops only grant-bound work.
- `require_financial_agent` currently checks identity, ancestry and live/shadow
  scope; it is also used during proposal validation. An Analysis Only mutation
  guard must not accidentally prevent the owner from proposing autonomy.
- Existing Goal permissions and operation-specific approvals also reach the
  financial executor. The new level must apply at its shared boundary, including
  resumed work and already approved operations, while reconciliation stays intact.
- Web/native settings already implement signing and authority review, but their
  advanced proposal builder requires bounded limits. It must be integrated into
  the composer experience, not exposed as another independent permission system.

## Implemented foundation

`packages/core/src/agent-permission.ts` defines the exact three semantic levels,
optional full-management customization, all duration presets and validation.
It preserves null limits and distinguishes pending/expired grants from active
autonomy. It does not grant authority or change the live executor.

## Remaining implementation

1. Server-owned per-Agent state, revisions and reusable draft persistence.
2. Serialized downgrade transitions revoking pending/active account grants and
   existing grant-bound autonomous work without closing broker positions.
3. Signature activation integration and trusted LLM permission context.
4. Shared financial mutation enforcement, including Goal and approval paths.
5. Composer popover/sheet, four-group editor, live summary and exact review on Web.
6. Equivalent native safe-area/keyboard/navigation/signing integration.
7. English/Arabic localization, simulated financial integration tests, responsive
   browser/native tests, required complete build, and final reviewable PR.

Hardware signing must not be reported as verified without a device test. The
mandate requires explicit owner authorization before merging or deploying.
