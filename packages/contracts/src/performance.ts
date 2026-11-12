/** An agent's results from broker-confirmed closes (mandate 5.5.4). */
export interface LabelResult {
  label: string;
  /** The account currency; amounts in different currencies are never added. */
  currency: string;
  count: number;
  /** Decimal string. */
  net_realized_pnl: string;
  /** Closes whose exit carried no broker profit; they add nothing to the net. */
  unpriced?: number;
}

export interface PerformanceSummary {
  closed_trades: LabelResult[];
  management: { label: string; count: number }[];
}
