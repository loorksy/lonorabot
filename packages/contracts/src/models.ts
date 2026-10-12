export type Provider = "openai" | "anthropic" | "deepseek" | "zai" | "openrouter";
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
