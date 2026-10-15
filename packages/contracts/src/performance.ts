export type ExecutionMode = "live" | "shadow";
export interface PerformanceSummary {
  execution_mode: ExecutionMode;
  sample_count: number;
  minimum_sample: number;
  sample_state: "sufficient_observations" | "insufficient_data";
  monetary_pnl: null;
  safety_policy_changed: false;
  live_authority_granted: false;
}
export interface ShadowTradeSummary {
  id: string;
  mode: "shadow";
  symbol: string;
  status: string;
  decision_id: string | null;
  payload: { action: string; volume?: string; fill_model?: string };
  state: { entry_price?: string; exit_price?: string; remaining_volume?: string };
}
