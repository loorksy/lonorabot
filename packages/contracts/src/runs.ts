import type { Payload } from "./domain";
export type ReplyStreamSnapshot = {
  turn_id: string;
  fence: number;
  generation: number;
  sequence: number;
  text: string;
  truncated: boolean;
  phase: "streaming" | "committed" | "discarded" | "failed" | "cancelled";
  message_id: string | null;
};
export type InputRequest = {
  id: string;
  run_id: string;
  message_id: string;
  question: string;
  choices: { id: string; label: string }[];
  status: "pending" | "answered" | "cancelled";
  selected_choice_id: string | null;
  answer_message_id: string | null;
};
export type Run = {
  input_requests?: InputRequest[];
  input_request?: InputRequest | null;
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
  stream?: ReplyStreamSnapshot | null;
  created_at: string;
  updated_at: string;
};

export type RunStatus = Run["status"];
