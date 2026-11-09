import type { Message } from "./domain";

/** «الملفات» are artifacts, «المعرفة» agent memory and semantic notes, «المهارات» installed skills. */
export type SearchCategory = "chats" | "messages" | "tasks" | "files" | "knowledge" | "skills";
export type SearchResult = {
  category: SearchCategory;
  id: string;
  title: string;
  /** Up to 160 characters centred on the hit. */
  snippet: string;
  created_at: string | null;
  thread_id?: string | null;
  seq?: number;
  role?: Message["role"];
  /** messages: the speaker; the hit's conversation is `thread_agent_id` or `group_id`. */
  agent_id?: string | null;
  /** messages: the agent whose thread holds the hit (null in a group's thread). */
  thread_agent_id?: string | null;
  group_id?: string | null;
  /** chats: agent | group; knowledge: memory | note. */
  kind?: string;
  status?: string | null;
  media_type?: string | null;
  size?: number | null;
  enabled?: boolean;
};
export type SearchResponse = {
  q: string;
  category: SearchCategory | null;
  limit: number;
  offset: number;
  counts: Partial<Record<SearchCategory, number>>;
  results: Partial<Record<SearchCategory, SearchResult[]>>;
};
