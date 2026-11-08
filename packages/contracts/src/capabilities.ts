/**
 * Capabilities (lonora_tools.capabilities, lonora_db.trusted_sources): what every agent
 * can use now and the owner's trusted-sources list. Presentation only; no capability
 * carries money authority.
 */
export type TrustedSourceKind =
  | "github"
  | "github_owner"
  | "github_repo"
  | "mcp_server"
  | "feed_domain";
/** What a trusted MCP server's tools may do; nothing that moves money is ever trusted. */
export type EffectTier = "read" | "write_nonfinancial";
export type TrustedSource = {
  id: string;
  kind: TrustedSourceKind;
  identifier: string;
  /** github.com, owner/repository, a domain, or the MCP server's saved name. */
  label: string | null;
  effect_tier: EffectTier;
  tools: string[];
  /** Trusted tools the server does not mark read-only: they run only at the write tier. */
  write_tools: string[];
  blocked_tools: string[];
  /** Copied from an operator declaration that no longer stands: it runs nothing until
   * the owner reviews the server. */
  needs_review: boolean;
  added_via: "default" | "operator" | "owner_ui" | "owner_card";
  added_by_agent_name: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};
export type CapabilitySkill = {
  resource_id: string;
  agent_id: string | null;
  agent_name: string | null;
  skill_id: string;
  version: string | null;
  provenance: "bundled" | "owner" | "agent_authored" | "external" | "unverified";
  repository: string | null;
  commit: string | null;
  enabled: boolean;
  /** The owner undid this version: it no longer loads. */
  undone: boolean;
  /** Undo can deny this version (an installed or agent-written Skill with a version). */
  can_undo: boolean;
  installed_at: string;
  updated_at: string;
};
export type CapabilityServer = {
  connection_id: string;
  name: string | null;
  enabled: boolean;
  credentials_configured: boolean;
  trusted_tier: EffectTier | null;
  trusted_tools: string[];
  write_tools: string[];
  blocked_tools: string[];
  operator_declared: number;
  trust_source_id: string | null;
  last_used_at: string | null;
};
export type CapabilityIntegration = {
  id: string;
  type: "brave_search" | "economic_calendar" | "news_feed" | "telegram" | "webhook";
  name: string | null;
  enabled: boolean;
  configured: boolean;
  /** A feed's domain only; its URL may carry a token. */
  domain: string | null;
  deliver_to_agent_name: string | null;
};
export type BuiltInCapabilityName =
  | "web_search"
  | "web_fetch"
  | "web_browse"
  | "news_feeds"
  | "economic_calendar"
  | "workspace_files"
  | "workspace_execution"
  | "chart_images"
  | "mcp_tools";
/** ready; not_connected: one owner card connects it; not_set_up: this server lacks it. */
export type CapabilityState = "ready" | "not_connected" | "not_set_up";
export type BuiltInCapability = {
  capability: BuiltInCapabilityName;
  state: CapabilityState;
  via: string | null;
};
/** GET /capabilities */
export type CapabilityReport = {
  trusted_sources: TrustedSource[];
  skills: CapabilitySkill[];
  mcp_servers: CapabilityServer[];
  integrations: CapabilityIntegration[];
  built_in: BuiltInCapability[];
};
/** POST /trusted-sources/mcp/{connection_id}/preview */
export type McpTrustPreview = {
  name: string;
  tools: string[];
  /** Tools that may change something: they run only when trusted for non-financial writes. */
  writes: string[];
  blocked: string[];
  unsupported: number;
  digest: string;
  trusted_tier: EffectTier | null;
};
