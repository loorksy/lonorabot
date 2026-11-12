/** An agent's results from broker-confirmed closes (mandate 5.5.4). */
export interface LabelResult {
  label: string;
  /** The account currency; amounts in different currencies are never added. */
  currency: string;
  count: number;
  /** Decimal string; null when no trade of the row has a known P&L (never zero). */
  net_realized_pnl: string | null;
  /** Closes whose exit carried no broker profit; they add nothing to the net. */
  unpriced?: number;
}

export interface PerformanceSummary {
  closed_trades: LabelResult[];
  management: { label: string; count: number }[];
}
