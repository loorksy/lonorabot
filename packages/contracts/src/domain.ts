import type { UiLock, UiState, UiSubmitRecord } from "./genui";
import type { AgentTemplate } from "./owner-actions";
import type { RichContent } from "./visual-response";

export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
export type Payload = Record<string, Json>;
export type Agent = {
  /**
   * The creation template; the client type derives from it, with role and scope_mode as
   * fallback. null for the personal agent and delegated helpers, whose role is their type.
   */
  template?: AgentTemplate | null;
  /** A signed grant is in force and the agent is not paused (presentation only). */
  trades_on_its_own?: boolean;
  role?: "personal" | "general" | "specialist" | "delegated" | "legacy";
  scope_mode?: "fixed_market" | "flexible";
  scope_revision?: number;
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
  /** Owner messages: the agent's run started on this message (two accent ticks). */
  consumed?: boolean | null;
  rich_content?: RichContent | null;
  client_nonce?: string | null;
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
  /** Who wrote it: the owner, a card's send (text composed by the server) or a v1 tap. */
  origin?: "owner" | "ui_submit" | "ui_follow_up";
  ui_submit?: UiSubmitRecord | null;
  ui_state?: UiState | null;
  /** Derived on read: the locking submission per card part. */
  ui_lock?: Record<string, UiLock>;
  /** Rule N on read: «مُعدّلة» or «لم يُنفَّذ». */
  ui_mark?: "superseded" | "not_run" | null;
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

export type GroupPayload = {
  name: string;
  member_ids: string[];
  participation: string;
  /** What the group is for (<= 160 characters). */
  purpose?: string;
  /** The member that answers when no agent is mentioned. */
  lead_agent_id?: string | null;
};
/** The owner's state of one conversation (ln_thread_prefs), shared by web and mobile. */
export type ThreadPrefs = {
  thread_id: string;
  last_read_seq: number;
  marked_unread: boolean;
  muted: boolean;
  archived: boolean;
  favourite: boolean;
  /** 1..3, newest pin on top; null when not pinned. */
  pinned_order: number | null;
  /** «مسح»: messages at or before this seq are hidden for the owner; 0 when nothing is hidden. */
  hidden_before_seq: number;
  updated_at: string | null;
};
export type ThreadPrefsUpdate = {
  pinned?: boolean;
  muted?: boolean;
  archived?: boolean;
  favourite?: boolean;
  marked_unread?: boolean;
};
/** «إبقاء المحادثات مؤرشفة». */
export type ThreadSettings = { keep_archived: boolean };
export type InboxMessageKind = "text" | "card" | "image" | "voice" | "file";
export type InboxLastMessage = {
  id: string;
  role: Message["role"];
  agent_id: string | null;
  content: string;
  created_at: string;
  seq: number;
  kind: InboxMessageKind;
  /** Server-derived one-line preview (<= 160 characters). */
  preview: string;
  attachments: { count: number; kinds: string[] };
  consumed: boolean | null;
};
export type InboxEntry = {
  thread_id: string;
  agent_id: string | null;
  group_id: string | null;
  last_message: InboxLastMessage | null;
  last_activity_at: string;
  unread_count: number;
  last_read_seq: number;
  marked_unread: boolean;
  muted: boolean;
  archived: boolean;
  favourite: boolean;
  pinned_order: number | null;
  hidden_before_seq: number;
};
export type ChatList = {
  id: string;
  name: string;
  position: number;
  thread_ids: string[];
  created_at: string;
  updated_at: string;
};
export type Group = Resource<GroupPayload> & { state: { thread_id?: string } };
export type Artifact = Resource<{
  name: string;
  media_type: string;
  size: number;
  key?: string;
  sha256?: string;
}>;
export type Usage = { input_tokens: number; output_tokens: number; cached_tokens: number };
