import type { Payload } from "./domain";
export type Run = {
  id: string;
  thread_id: string;
  agent_id: string;
  parent_run_id: string | null;
  status:
    | "queued"
    | "leased"
    | "running"
    | "waiting_input"
    | "waiting_takeover"
    | "completed"
    | "failed"
    | "cancelled";
  trigger: string;
  error_code: string | null;
  result: string | null;
  model_metadata: Payload;
  created_at: string;
  updated_at: string;
};

export type RunStatus = Run["status"];
