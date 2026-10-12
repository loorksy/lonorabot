import { api } from "./api";
export type VoiceJoin = { session_id: string; room: string; url: string; token: string };
export const startVoice = (agent_id: string, thread_id: string) =>
  api.post<VoiceJoin>("/voice/sessions", { agent_id, thread_id, mode: "pipeline" });
export const stopVoice = (id: string) => api.delete(`/voice/sessions/${id}`);
export const interruptVoice = (id: string) => api.post(`/voice/sessions/${id}/interrupt`, {});
