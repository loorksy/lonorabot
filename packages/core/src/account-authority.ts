import type {
  AccountAuthority,
  AccountAuthorityProposal,
  AuthorityAction,
  DeviceChallenge,
  DeviceProof,
} from "@lonora/contracts";

export const authorityLimitFields = [
  "maximum_order_volume",
  "maximum_symbol_volume",
  "maximum_positions",
  "maximum_pending_orders",
  "maximum_actions",
  "minimum_equity",
  "valid_until",
] as const;
export type AuthorityLimit = (typeof authorityLimitFields)[number];
export type AuthorityDraft = Record<AuthorityLimit, string>;
export const emptyAuthorityDraft = (): AuthorityDraft => ({
  maximum_order_volume: "",
  maximum_symbol_volume: "",
  maximum_positions: "",
  maximum_pending_orders: "",
  maximum_actions: "",
  minimum_equity: "",
  valid_until: "",
});

/** Client validation is UX only; the server independently validates every field. */
export function authorityProposal(
  draft: AuthorityDraft,
  scope: {
    thread_id: string;
    account_id: string;
    symbols: string[];
    actions: AuthorityAction[];
    allow_manual_positions: boolean;
  },
  now = Date.now(),
): AccountAuthorityProposal | null {
  if (
    !scope.thread_id ||
    !scope.account_id ||
    !scope.symbols.length ||
    !scope.actions.length ||
    scope.symbols.length > 100 ||
    new Set(scope.symbols).size !== scope.symbols.length ||
    new Set(scope.actions).size !== scope.actions.length ||
    scope.symbols.some((s) => !s || s.trim() !== s || s.length > 80)
  )
    return null;
  const numeric = ["maximum_order_volume", "maximum_symbol_volume", "minimum_equity"] as const;
  for (const field of numeric)
    if (
      !/^\d+(\.\d+)?$/.test(draft[field]) ||
      !Number.isFinite(Number(draft[field])) ||
      Number(draft[field]) <= 0
    )
      return null;
  if (Number(draft.maximum_order_volume) > Number(draft.maximum_symbol_volume)) return null;
  const integer = (value: string, min: number, max: number) =>
    /^\d+$/.test(value) &&
    Number.isSafeInteger(Number(value)) &&
    Number(value) >= min &&
    Number(value) <= max;
  if (
    !integer(draft.maximum_positions, 1, 100) ||
    !integer(draft.maximum_pending_orders, 0, 100) ||
    !integer(draft.maximum_actions, 1, 10000)
  )
    return null;
  // Require explicit timezone. Never reinterpret an ambiguous local date silently.
  if (!/(Z|[+-]\d\d:\d\d)$/.test(draft.valid_until)) return null;
  const expiry = Date.parse(draft.valid_until);
  if (!Number.isFinite(expiry) || expiry <= now || expiry > now + 30 * 86400000) return null;
  return {
    ...scope,
    maximum_order_volume: draft.maximum_order_volume,
    maximum_symbol_volume: draft.maximum_symbol_volume,
    minimum_equity: draft.minimum_equity,
    maximum_positions: Number(draft.maximum_positions),
    maximum_pending_orders: Number(draft.maximum_pending_orders),
    maximum_actions: Number(draft.maximum_actions),
    valid_until: new Date(expiry).toISOString(),
  };
}
export function authorityStatus(
  row: AccountAuthority,
  now = Date.now(),
): AccountAuthority["status"] {
  if (row.status === "revoked" || row.status === "expired") return row.status;
  if (
    Date.parse(row.valid_until) <= now ||
    !Number.isFinite(Date.parse(row.valid_until)) ||
    (row.status === "pending" &&
      (!Number.isFinite(Date.parse(row.activation_expires_at)) ||
        Date.parse(row.activation_expires_at) <= now))
  )
    return "expired";
  return row.status;
}

export type AuthorityTransport = { post<T>(path: string, body: unknown): Promise<T> };
/** Only the authenticated server response can establish active authority. */
export async function activateAccountAuthority(
  transport: AuthorityTransport,
  row: AccountAuthority,
  prove: (challenge: DeviceChallenge, enroll?: boolean) => Promise<DeviceProof>,
): Promise<AccountAuthority> {
  if (authorityStatus(row) !== "pending") throw new Error("account_authority_expired_or_used");
  const challenge = await transport.post<DeviceChallenge>(
    `/account-authorities/${encodeURIComponent(row.id)}/challenge`,
    {},
  );
  const proof = await prove(challenge);
  const updated = await transport.post<AccountAuthority>("/account-authorities/verify", proof);
  if (
    updated.id !== row.id ||
    updated.agent_id !== row.agent_id ||
    updated.account_id !== row.account_id ||
    updated.thread_id !== row.thread_id ||
    JSON.stringify(Object.entries(updated.envelope).sort(([a], [b]) => a.localeCompare(b))) !==
      JSON.stringify(Object.entries(row.envelope).sort(([a], [b]) => a.localeCompare(b)))
  )
    throw new Error("account_authority_scope_changed");
  if (authorityStatus(updated) !== "active")
    throw new Error("account_authority_activation_unconfirmed");
  return updated;
}
