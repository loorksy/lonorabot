export type Owner = { id: string; email: string };
export type Agent = {
  id: string;
  name: string;
  avatar: string;
  color: string;
  instructions: string;
  paused: boolean;
  parent_id: string | null;
  created_at: string;
};
export type Thread = {
  id: string;
  agent_id: string | null;
  group_id: string | null;
  title: string;
  created_at: string;
};
export type Message = {
  id: string;
  seq: number;
  thread_id: string;
  agent_id: string | null;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  attachment_ids: string[];
  created_at: string;
};
export type RunStatus =
  | "queued"
  | "leased"
  | "running"
  | "waiting_input"
  | "waiting_takeover"
  | "completed"
  | "failed"
  | "cancelled";
export type Run = {
  id: string;
  agent_id: string;
  thread_id: string;
  status: RunStatus;
  error_code: string | null;
  created_at: string;
};
export type Group = {
  id: string;
  payload: { name: string; member_ids: string[]; participation: string };
  state: { thread_id?: string };
};
export type Artifact = { id: string; payload: { name: string; media_type: string; size: number } };
export type Routing = {
  mode: "unified" | "custom";
  unified: { provider: string; model: string } | null;
  routes: Record<string, { provider: string; model: string }>;
};
export type Usage = { input_tokens: number; output_tokens: number; cached_tokens: number };
export const activeStatuses: RunStatus[] = ["queued", "leased", "running"];
