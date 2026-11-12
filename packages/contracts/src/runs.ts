import type { Payload } from "./domain";
import type { RichContent } from "./visual-response";
export type ReplyStreamSnapshot = {
  input_seq?: number;
  turn_id: string;
  fence: number;
  generation: number;
  sequence: number;
  text: string;
  truncated: boolean;
  phase: "streaming" | "committed" | "discarded" | "failed" | "cancelled";
  message_id: string | null;
  /** Cumulative, server-validated complete frames; never a raw partial document. */
  rich_content?: RichContent | null;
};
/** What picking a choice makes the agent do: its calls, by tool, never their arguments. */
export type ChoiceEffect = {
  name: string;
  toolset: string;
  effect: "read" | "change";
  count: number;
};
export type InputRequest = {
  id: string;
  run_id: string;
  message_id: string;
  /** The thread whose message holds the question: a background run's question is copied
   * into the conversation it reports to, while the run itself keeps its own thread. */
  thread_id: string;
  question: string;
  choices: { id: string; label: string; effects?: ChoiceEffect[] }[];
  status: "pending" | "answered" | "cancelled";
  selected_choice_id: string | null;
  answer_message_id: string | null;
};
/** Why a Run failed, by the provider's error family (Q22); on `run.failed` and Run. */
export type RunFailure = {
  family: "quota" | "rate" | "timeout" | "model" | "other";
  /** The provider's own Retry-After hint, counted from the failure; null without one. */
  retry_after_seconds: number | null;
};

export type Run = {
  input_seq?: number;
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
  /** Background work (VISION 11.5): no one waits on its reply, so its failure is shown in
   * the conversation only when the owner must fix it (model access, quota). The server
   * always sends it. */
  background?: boolean;
  error_code: string | null;
  /** Present on a failed Run. */
  failure?: RunFailure | null;
  result: string | null;
  model_metadata: Payload;
  stream?: ReplyStreamSnapshot | null;
  created_at: string;
  updated_at: string;
};

export type RunStatus = Run["status"];
