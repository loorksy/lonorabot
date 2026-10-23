/** Owner-confirmed account delegation. Reading this projection grants no authority. */
export const authorityActions = [
  "buy",
  "sell",
  "buy_limit",
  "sell_limit",
  "buy_stop",
  "sell_stop",
  "close_position",
  "modify_position",
  "cancel_order",
  "modify_order",
] as const;
export type AuthorityAction = (typeof authorityActions)[number];
export type AccountAuthorityProposal = {
  thread_id: string;
  account_id: string;
  management_mode?: "bounded" | "full";
  symbol_scope?: "selected" | "account";
  symbols: string[];
  actions: AuthorityAction[];
  maximum_order_volume: string | null;
  maximum_symbol_volume: string | null;
  maximum_positions: number | null;
  maximum_pending_orders: number | null;
  maximum_actions: number | null;
  minimum_equity: string | null;
  valid_until: string | null;
  allow_manual_positions: boolean;
};
export type AccountAuthority = {
  id: string;
  agent_id: string;
  thread_id: string;
  account_id: string;
  status: "pending" | "active" | "revoked" | "expired";
  envelope: AccountAuthorityProposal & {
    owner_id: string;
    agent_id: string;
    execution_mode: "live";
    schema_version: 1 | 2;
  };
  activation_expires_at: string;
  valid_until: string | null;
  created_at: string;
  updated_at: string;
  monetary_stop_risk: "unavailable";
};
