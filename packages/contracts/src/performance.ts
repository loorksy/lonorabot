/** An agent's results from broker-confirmed closes (mandate 5.5.4). */
export interface LabelResult {
  /** The group: the fields of `group_by` (label by default). */
  label?: string;
  symbol?: string;
  session?: string | null;
  side?: string;
  /** Scope team read by Lonora: the agent, or null for the owner's own tickets. */
  agent_id?: string | null;
  /** The account currency; amounts in different currencies are never added. */
  currency: string;
  count: number;
  /** By the sign of the net P&L, of the priced trades: a win rate always with its sample. */
  outcomes: { wins: number; losses: number; flat: number; of: number };
  /** Decimal string; null when no trade of the row has a known P&L (never zero). */
  net_realized_pnl: string | null;
  /** Closes whose exit carried no broker profit; they add nothing to the net. */
  unpriced?: number;
  /** R in units of each trade's initial risk, as decimal strings; never estimated. */
  r: {
    n: number;
    mean: string | null;
    sum: string | null;
    mean_win: string | null;
    mean_loss: string | null;
    /** Trades without R, by reason code (no_initial_stop, unpriced, ...). */
    unknown?: Record<string, number>;
  };
}

export interface PerformanceSummary {
  closed_trades: LabelResult[];
  management: { label: string; count: number }[];
  /** Present when only the latest closed trades (this many) were read. */
  latest_trades_read?: number;
}
