/**
 * Usage dashboard (WP-I). A view of what requests cost at list price, never a cap
 * (owner decisions D4 and Q22). Server: GET /api/usage/series, /usage/rank,
 * /usage/export.csv and /usage/agents?bucket=day.
 */
export type UsagePeriod = "day" | "week" | "month";
export type UsageBucket = "hour" | "day";

/**
 * `input_tokens` counts every prompt token, cached included; `cached_tokens` is the part
 * served from cache; `tokens` = input + output. `cost_usd` sums the requests whose model
 * has a list price; `unpriced_requests` counts the others (cost unknown, never guessed).
 */
export type UsageFigures = {
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  tokens: number;
  requests: number;
  unpriced_requests: number;
};
export type UsageWindow = { start: string; end: string };
/** The equal preceding window, cut at the same elapsed point as the current one. */
export type UsagePreviousWindow = UsageWindow & UsageFigures;
/** One hour or day; every figure is null for an hour of today that has not started. */
export type UsagePoint = { start: string } & { [K in keyof UsageFigures]: UsageFigures[K] | null };
/** Month to date in the owner's zone and its linear projection; there is no limit. */
export type UsageMonth = {
  start: string;
  spent_usd: number;
  projected_usd: number;
  days_in_month: number;
  day_of_month: number;
  unpriced_requests: number;
};
export type UsageSeries = {
  period: UsagePeriod;
  /** hour for `day` (24 points, today), day for `week` (7) and `month` (30). */
  bucket: UsageBucket;
  timezone: string;
  agent_id: string | null;
  /** The date the server's price list was recorded. */
  prices_as_of: string;
  /** From local midnight of the first day to now. */
  window: UsageWindow;
  previous: UsagePreviousWindow;
  points: UsagePoint[];
  totals: UsageFigures;
  month: UsageMonth;
};
export type UsageRankAgent = UsageFigures & { agent_id: string | null; agent_name: string | null };
/** `cost_usd` is null when the model has no list price. */
export type UsageRankModel = Omit<UsageFigures, "cost_usd"> & {
  provider: string;
  model: string;
  cost_usd: number | null;
};
/** Sorted by cost, then tokens, largest first. */
export type UsageRank = {
  period: UsagePeriod;
  timezone: string;
  agent_id: string | null;
  prices_as_of: string;
  window: UsageWindow;
  totals: UsageFigures;
  agents: UsageRankAgent[];
  models: UsageRankModel[];
};
/** One local day (YYYY-MM-DD) of /usage/agents?bucket=day. */
export type UsageDay = UsageFigures & { date: string };
