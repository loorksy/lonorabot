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
  execution_mode?: "live" | "shadow";
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
  /** The owner's name for the schedule; null on older routines (show the prompt). */
  title: string | null;
  prompt: string;
  goal_id: string | null;
  step_id: string | null;
  interval_seconds: number | null;
  cron: string | null;
  /** A one-shot routine («مرة واحدة») fires once at this time, then switches off. */
  run_at: string | null;
  timezone: string;
  enabled: boolean;
  next_run_at: string;
};
/** What a routine save sends: exactly one of interval_seconds, cron or run_at. */
export type RoutineInput = {
  title?: string | null;
  prompt: string;
  interval_seconds?: number | null;
  cron?: string | null;
  run_at?: string | null;
  timezone?: string;
  enabled?: boolean;
};
/** A light goal of a non-trading agent (Q41): a note, never a schedule or an authority. */
export type AgentGoal = { title: string; description: string; done: boolean };
/** A «رابط» knowledge entry (Q40). */
export type KnowledgeLink = { title: string; url: string; note: string };
/** One row of «المعرفة»: a semantic note or a link. */
export type KnowledgeItem = {
  id: string;
  type: "note" | "link";
  title: string;
  content: string;
  url: string | null;
  version: number | null;
  updated_at: string;
};
/** One saved version of a skill («سجل الإصدارات»). */
export type SkillVersionEntry = {
  version: number;
  created_at: string;
  name: string;
  description: string;
  enabled: boolean;
  current: boolean;
};
export type ActivityCode =
  | "agent_created"
  | "authority_changed"
  | "limits_changed"
  | "restriction_set"
  | "restriction_lifted"
  | "operation_resolved"
  | "approval_approved"
  | "approval_rejected"
  | "task_created"
  | "task_completed"
  | "task_cancelled"
  | "skill_created"
  | "skill_updated"
  | "supervision_granted"
  | "supervision_revoked"
  | "watch_triggered"
  | "goal_created"
  | "knowledge_added";
/** One «سجل الإجراءات» row, projected by the server from a durable event (Q45). */
export type ActivityEntry = {
  id: string;
  code: ActivityCode;
  agent_id: string | null;
  thread_id: string | null;
  subject: string;
  created_at: string;
};
export type ActivityPage = { items: ActivityEntry[]; next_before: number | null };

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
