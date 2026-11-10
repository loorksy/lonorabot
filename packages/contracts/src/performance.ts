export interface PerformanceSummary {
  sample_count: number;
  minimum_sample: number;
  sample_state: "sufficient_observations" | "insufficient_data";
  monetary_pnl: null;
  safety_policy_changed: false;
  live_authority_granted: false;
}
