export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
export type Payload = Record<string, Json>;
export type Agent = {
  super_bot_active?: boolean;
  execution_mode?: "live" | "shadow";
  role?: "personal" | "specialist" | "delegated" | "legacy";
  title?: string;
  description?: string;
  id: string;
  name: string;
  avatar: string;
  color: string;
  instructions: string;
  paused: boolean;
  parent_id: string | null;
  trading_account_id?: string | null;
  trading_symbol?: string | null;
  created_at: string;
};
export type Thread = {
  id: string;
  agent_id: string | null;
  group_id: string | null;
  title: string;
  created_at: string;
};
export type InputAnswer = { run_id: string; question_id: string; choice_id: string };
export type Message = {
  mentions?: { agent_ids: string[]; all: boolean; session_id?: string | null };
  id: string;
  thread_id: string;
  agent_id: string | null;
  seq: number;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  reply_to: string | null;
  attachment_ids: string[];
  created_at: string;
};
export type Resource<T = Payload> = {
  id: string;
  agent_id: string | null;
  thread_id: string | null;
  payload: T;
  state?: Payload;
  version: number;
  created_at: string;
  updated_at: string;
};
export type Routine = {
  id: string;
  agent_id: string;
  thread_id: string;
  prompt: string;
  interval_seconds: number | null;
  cron: string | null;
  timezone: string;
  enabled: boolean;
  next_run_at: string;
};

export type GroupPayload = { name: string; member_ids: string[]; participation: string };
export type Group = Resource<GroupPayload> & { state: { thread_id?: string } };
export type Artifact = Resource<{
  name: string;
  media_type: string;
  size: number;
  key?: string;
  sha256?: string;
}>;
export type Usage = { input_tokens: number; output_tokens: number; cached_tokens: number };
