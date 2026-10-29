import type {
  AccountAuthority,
  AccountAuthorityProposal,
  AgentPermissionLevel,
  AuthorityDuration,
  ManagementCustomization,
} from "@lonora/contracts";
import { authorityActions } from "@lonora/contracts";
import { authorityStatus } from "./account-authority";

export const agentPermissionLevels = ["analysis", "supervised", "autonomous"] as const;
export type {
  AgentPermissionLevel,
  AuthorityDuration,
  ManagementCustomization,
} from "@lonora/contracts";
export const numericalAuthorityLimits = [
  "maximum_order_volume",
  "maximum_symbol_volume",
  "maximum_positions",
  "maximum_pending_orders",
  "maximum_actions",
  "minimum_equity",
] as const;

export function emptyManagementCustomization(): ManagementCustomization {
  return {
    actions: [...authorityActions],
    limits: {
      maximum_order_volume: "",
      maximum_symbol_volume: "",
      maximum_positions: "",
      maximum_pending_orders: "",
      maximum_actions: "",
      minimum_equity: "",
    },
    duration: "until_stopped",
    allow_manual_positions: true,
  };
}

/** Approval behavior is independent of bounded/full numerical scope. Never
 * promote a pending/expired grant, or infer authority from a saved UI draft.
 */
export function permissionFromAuthority(
  row: AccountAuthority,
  now = Date.now(),
): AgentPermissionLevel | null {
  return authorityStatus(row, now) === "active" ? "autonomous" : null;
}

/** Builds only the existing v2 full-management contract. Absence of an optional
 * limit remains null; blank values never become zero or an invented ceiling.
 * The server must validate scope and obtain a new signature before activation.
 */
export function customizedManagementProposal(
  draft: ManagementCustomization,
  scope: {
    thread_id: string;
    account_id: string;
    symbol_scope: "selected" | "account";
    symbols: string[];
  },
  now = Date.now(),
): AccountAuthorityProposal | null {
  if (
    !scope.thread_id ||
    !scope.account_id ||
    !Number.isFinite(now) ||
    !draft.actions.length ||
    draft.actions.length > 10 ||
    new Set(draft.actions).size !== draft.actions.length ||
    draft.actions.some((action) => !authorityActions.includes(action))
  )
    return null;
  if (
    !["selected", "account"].includes(scope.symbol_scope) ||
    (scope.symbol_scope === "selected" ? !scope.symbols.length : scope.symbols.length !== 0)
  )
    return null;
  if (
    scope.symbols.length > 100 ||
    new Set(scope.symbols).size !== scope.symbols.length ||
    scope.symbols.some((s) => !s || s !== s.trim() || s.length > 80)
  )
    return null;
  const limits: Record<string, string | number | null> = {};
  for (const field of numericalAuthorityLimits) {
    const raw = draft.limits[field];
    if (raw === "") {
      limits[field] = null;
      continue;
    }
    const integer = ["maximum_positions", "maximum_pending_orders", "maximum_actions"].includes(
      field,
    );
    if (!(integer ? /^\d+$/ : /^\d+(\.\d+)?$/).test(raw)) return null;
    if (integer) {
      const value = Number(raw);
      if (
        !Number.isSafeInteger(value) ||
        value < (field === "maximum_pending_orders" ? 0 : 1) ||
        value > (field === "maximum_actions" ? 10000 : 100)
      )
        return null;
      limits[field] = value;
    } else {
      // These are Decimal fields on the server. Keep their exact value rather
      // than rounding through JavaScript's floating-point representation.
      if (!/[1-9]/.test(raw)) return null;
      limits[field] = raw;
    }
  }
  if (
    limits.maximum_order_volume !== null &&
    limits.maximum_symbol_volume !== null &&
    decimalExceeds(String(limits.maximum_order_volume), String(limits.maximum_symbol_volume))
  )
    return null;
  const hours: Record<AuthorityDuration, number | null> = {
    until_stopped: null,
    "12h": 12,
    "24h": 24,
    "7d": 168,
  };
  const duration = hours[draft.duration];
  if (duration === undefined) return null;
  const expiry = duration === null ? null : new Date(now + duration * 3600000);
  if (expiry !== null && !Number.isFinite(expiry.getTime())) return null;
  return {
    ...scope,
    symbols: [...scope.symbols],
    management_mode: "full",
    actions: [...draft.actions],
    maximum_order_volume: limits.maximum_order_volume as string | null,
    maximum_symbol_volume: limits.maximum_symbol_volume as string | null,
    maximum_positions: limits.maximum_positions as number | null,
    maximum_pending_orders: limits.maximum_pending_orders as number | null,
    maximum_actions: limits.maximum_actions as number | null,
    minimum_equity: limits.minimum_equity as string | null,
    valid_until: expiry?.toISOString() ?? null,
    allow_manual_positions: draft.allow_manual_positions,
  };
}

function decimalExceeds(left: string, right: string): boolean {
  const [leftWhole, leftFraction = ""] = left.split(".");
  const [rightWhole, rightFraction = ""] = right.split(".");
  const wholeA = leftWhole.replace(/^0+/, "") || "0";
  const wholeB = rightWhole.replace(/^0+/, "") || "0";
  if (wholeA.length !== wholeB.length) return wholeA.length > wholeB.length;
  if (wholeA !== wholeB) return wholeA > wholeB;
  const digits = Math.max(leftFraction.length, rightFraction.length);
  return leftFraction.padEnd(digits, "0") > rightFraction.padEnd(digits, "0");
}
