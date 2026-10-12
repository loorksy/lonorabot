import { api, type Capability, type Routing } from "./api";
export const capabilities: Capability[] = [
  "conversation",
  "reasoning",
  "research",
  "vision",
  "realtime_voice",
  "stt",
  "tts",
  "background",
];
export const readRouting = () => api.get<Routing>("/settings/models");
export const saveRouting = (routing: Routing) => api.put<Routing>("/settings/models", routing);
