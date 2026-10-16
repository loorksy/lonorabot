export type SuperBotRequest = {
  id: string;
  agent_id: string;
  thread_id: string;
  goal_id: string;
  mode: "advisory" | "supervised" | "autonomous";
  status: "pending" | "activated" | "expired" | "rejected" | "cancelled" | "paused" | "disabled";
  envelope: {
    goal_id: string;
    account_id: string;
    symbol: string;
    mode: "advisory" | "supervised" | "autonomous";
    maximum_volume: string | null;
    max_trade_actions: number;
    allow_manual_positions: boolean;
    execution_mode: "live" | "shadow";
    goal_title: string;
    objective: string;
    steps: {
      id: string;
      title: string;
      trade: {
        action: string;
        symbol: string;
        price?: string | null;
        position_id?: string | null;
        order_id?: string | null;
        target_step_id?: string | null;
        volume: string | null;
        stop_loss?: string | null;
        take_profit?: string | null;
      } | null;
    }[];
  };
  expires_at: string;
};
export type DeviceChallenge = { challenge_id: string; publicKey: Record<string, unknown> };
export type DeviceProof = { challenge_id: string; credential: Record<string, unknown> };
