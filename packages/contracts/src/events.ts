import type { Payload } from "./domain";
export type Event = {
  cursor: number;
  kind: string;
  thread_id: string | null;
  agent_id: string | null;
  run_id: string | null;
  payload: Payload;
  created_at: string;
};
