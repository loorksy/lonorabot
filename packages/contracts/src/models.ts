import type { UsageDay } from "./usage";

export type Provider =
  | "openai"
  | "anthropic"
  | "deepseek"
  | "zai"
  | "openrouter"
  | "openai_compatible";
export type Capability =
  | "conversation"
  | "reasoning"
  | "research"
  | "vision"
  | "realtime_voice"
  | "stt"
  | "tts"
  | "background";
export type Selection = { provider: Provider; model: string };
export type Routing = {
  mode: "unified" | "custom";
  unified: Selection | null;
  routes: Partial<Record<Capability, Selection>>;
};
export type Model = {
  id: string;
  provider: Provider;
  name: string;
  capabilities: string[];
  verified: boolean;
  source: string;
  context_window: number | null;
};
/** "automatic": Lonora chooses (the owner's default model; the agent may switch itself
 * among the allowed models). "fixed": the owner chose one model; only the owner changes it. */
export type AgentModelMode = "automatic" | "fixed";
export type AgentModelPreference = { primary: Selection | null; fallbacks: Selection[] };
export type AgentModelState = { mode: AgentModelMode; preference: AgentModelPreference };
/** One agent's model choice (lonora_db.agent_models); it never grants authority. */
export type AgentModelRecord = {
  owner_id: string;
  agent_id: string;
  revision: number;
  mode: AgentModelMode;
  preference: AgentModelPreference;
  chosen_by: "owner" | "agent" | null;
  chosen_by_agent_id: string | null;
  previous: AgentModelState | null;
  changed_at: string | null;
};
export type AgentModelChange = {
  mode: AgentModelMode;
  primary?: Selection | null;
  fallbacks?: Selection[];
  expected_revision?: number;
};
/** A model as the owner recognizes it: the catalog name when known. */
export type ModelLabel = { provider: Provider | null; model: string | null; name: string | null };
export type ModelUsage = {
  provider: Provider;
  model: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  /** USD at list price; null when the model has no list price. */
  cost_usd: number | null;
};
/** Model usage of one agent over a period; a view, never a cap (owner decision D4). */
export type AgentUsage = {
  agent_id: string | null;
  agent_name: string | null;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  last_used_at: string | null;
  /** USD at list price of the priced requests; `unpriced_requests` have no known cost. */
  cost_usd: number;
  unpriced_requests: number;
  models: ModelUsage[];
};
/** GET /usage/agents; with `bucket=day`, `since` is local midnight and `buckets` one per day. */
export type AgentUsageReport = {
  days: number;
  since: string;
  agents: AgentUsage[];
  bucket?: "day";
  timezone?: string;
  buckets?: UsageDay[];
};
/** Everything an agent's model card shows (GET /agents/{id}/model/summary). */
export type AgentModelSummary = {
  record: AgentModelRecord;
  current: ModelLabel;
  allowed: ModelLabel[];
  available: Array<{ provider: Provider; model: string; name: string }>;
  connected_providers: Provider[];
  usage: Omit<
    AgentUsage,
    "agent_id" | "agent_name" | "last_used_at" | "cost_usd" | "unpriced_requests"
  > & { days: number };
};
/** The owner's allowed models: the global routes and backups, plus additions. */
export type AllowedModels = { routed: Selection[]; added: Selection[] };
