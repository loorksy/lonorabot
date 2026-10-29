import type { AccountAuthority, AuthorityAction } from "./account-authority";

export type AgentPermissionLevel = "analysis" | "supervised" | "autonomous";
export type AuthorityDuration = "until_stopped" | "12h" | "24h" | "7d";
export type ManagementCustomization = {
  actions: AuthorityAction[];
  limits: Record<
    | "maximum_order_volume"
    | "maximum_symbol_volume"
    | "maximum_positions"
    | "maximum_pending_orders"
    | "maximum_actions"
    | "minimum_equity",
    string
  >;
  duration: AuthorityDuration;
  allow_manual_positions: boolean;
};
export type PermissionCustomization = ManagementCustomization & {
  account_id: string;
  symbol_scope: "selected" | "account";
  symbols: string[];
};
/** This authenticated server projection describes permission; drafts never grant it. */
export type PermissionState = {
  agent_id: string;
  revision: number;
  effective_level: AgentPermissionLevel;
  fallback_level: "analysis" | "supervised";
  requested_level: AgentPermissionLevel;
  status:
    | "analysis"
    | "supervised"
    | "autonomous"
    | "awaiting_authorization"
    | "authorization_expired"
    | "autonomous_stopped";
  active_authorities: AccountAuthority[];
  pending_authority: AccountAuthority | null;
  customization: PermissionCustomization | null;
};
export type AgentPermissionState = PermissionState;
export type AgentPermissionCustomization = PermissionCustomization;
export type PermissionChange = {
  level: "analysis" | "supervised";
  expected_revision: number;
};
