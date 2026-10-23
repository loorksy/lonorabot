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
  symbols: string[];
  actions: AuthorityAction[];
  maximum_order_volume: string;
  maximum_symbol_volume: string;
  maximum_positions: number;
  maximum_pending_orders: number;
  maximum_actions: number;
  minimum_equity: string;
  valid_until: string;
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
    schema_version: 1;
  };
  activation_expires_at: string;
  valid_until: string;
  created_at: string;
  updated_at: string;
  monetary_stop_risk: "unavailable";
};
