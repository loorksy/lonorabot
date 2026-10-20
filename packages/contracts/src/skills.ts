export type SkillActivation = {
  mode: "automatic" | "explicit" | "trigger_based";
  intents: string[];
  triggers: string[];
};

export type SkillManifest = {
  id: string;
  version: string;
  title: string;
  description: string;
  source: "builtin" | "owner" | "installed" | "external" | "legacy";
  stability: "stable" | "experimental" | "legacy";
  activation: SkillActivation;
  risk_class: "read_only" | "state_mutating" | "external_action" | "financial";
  required_capabilities: string[];
  required_tools: string[];
  dependencies: string[];
  conflicts: string[];
  priority: number;
  context_budget: number;
};

export type AgentSkill = {
  name: string;
  content: string;
  enabled: boolean;
  manifest: SkillManifest | null;
};

export type SkillRevocationReason = "owner_revoked" | "regression" | "unsafe" | "superseded";
export type SkillVersionControls = {
  owner_id: string;
  agent_id: string;
  revision: number;
  revoked: {
    skill_id: string;
    version: string;
    revoked_at: string;
    reason: SkillRevocationReason;
  }[];
};

// Current catalog availability is not a claim about instructions pinned in a Run.
export type SkillCatalogEntry = {
  id: string;
  version: string | null;
  title: string;
  description: string;
  source: SkillManifest["source"] | null;
  available: boolean;
  code: string | null;
  manifest: SkillManifest | null;
  resource_id: string | null;
  resource_version: number | null;
};

export type SkillCatalog = {
  agent_id: string;
  items: SkillCatalogEntry[];
  total: number;
  next_offset: number | null;
};

export type SkillCatalogDetail = SkillCatalogEntry & { content: string };
