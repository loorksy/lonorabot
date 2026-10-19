import type {
  Agent,
  Artifact,
  AttentionNotification,
  Group,
  Message,
  Run,
  Thread,
  TradeApproval,
} from "@lonora/contracts";
import { registerSessionTeardown } from "./session-lifecycle";

export type InboxEntry = {
  thread_id: string;
  agent_id: string | null;
  group_id: string | null;
  last_message: Pick<Message, "id" | "role" | "content" | "created_at" | "seq"> | null;
  last_activity_at: string;
};
export type InboxSnapshot = {
  agents: Agent[];
  groups: Group[];
  runs: Run[];
  inbox: InboxEntry[];
  attention: AttentionNotification[];
};
export type ConversationSnapshot = {
  thread: Thread | null;
  agents: Agent[];
  groups: Group[];
  messages: Message[];
  runs: Run[];
  files: Artifact[];
  approvals: TradeApproval[];
  collaborationActive: boolean;
  collaborationSessionId?: string;
  loaded: boolean;
  hasOlder: boolean;
};
type Scope = { identity: string; generation: number };

// Navigation cache only: never persisted, never a source of financial authority.
// A generation fences late responses after logout, including login by the same owner.
export class ConversationCache {
  private generation = 0;
  private scope: Scope | null = null;
  private entries = new Map<string, { value: unknown; at: number }>();
  constructor(
    private readonly now = Date.now,
    private readonly limit = 32,
  ) {}
  activate(server: string, ownerId: string): Scope {
    const identity = JSON.stringify([server, ownerId]);
    if (this.scope?.identity !== identity) {
      this.clear();
      this.scope = { identity, generation: this.generation };
    }
    return this.scope;
  }
  current(scope: Scope | null): boolean {
    return Boolean(scope && this.scope === scope && scope.generation === this.generation);
  }
  get<T>(scope: Scope | null, key: string): T | undefined {
    if (!this.current(scope)) return;
    const entry = this.entries.get(key);
    if (!entry) return;
    if (this.now() - entry.at > 15 * 60_000) {
      this.entries.delete(key);
      return;
    }
    this.entries.delete(key);
    this.entries.set(key, entry);
    return entry.value as T;
  }
  set<T>(scope: Scope | null, key: string, value: T) {
    if (!this.current(scope)) return;
    this.entries.delete(key);
    this.entries.set(key, { value, at: this.now() });
    while (this.entries.size > this.limit) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) break;
      this.entries.delete(oldest);
    }
  }
  remove(scope: Scope | null, key: string) {
    if (this.current(scope)) this.entries.delete(key);
  }
  clear() {
    this.generation += 1;
    this.scope = null;
    this.entries.clear();
  }
}
export const conversationCache = new ConversationCache();
registerSessionTeardown(async () => conversationCache.clear());
