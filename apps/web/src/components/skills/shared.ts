import { t } from "@lingui/core/macro";
import type { SkillManifest, SkillRevocationReason } from "@lonora/contracts";
import { useEffect, useRef } from "react";

export const SEMVER = "(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)";

export function useAlive() {
  const live = useRef(false);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  return live;
}

export function sourceLabel(source: SkillManifest["source"] | null) {
  switch (source) {
    case "builtin":
      return t`Built in`;
    case "owner":
      return t`Owner instructions`;
    case "legacy":
      return t`Legacy instructions`;
    case "installed":
    case "external":
      return t`Owner-supplied source`;
    default:
      return t`Unverified metadata`;
  }
}

export function statusLabel(code: string | null) {
  switch (code) {
    case "skill_disabled":
      return t`Disabled`;
    case "skill_version_revoked":
      return t`Version blocked`;
    case "skill_dependency_unavailable":
    case "skill_reference_missing":
    case "skill_dependency_cycle":
      return t`Dependency unavailable`;
    case "skill_builtin_override_denied":
      return t`Built-in override rejected`;
    case "skill_context_budget_exceeded":
    case "skill_total_budget_exceeded":
      return t`Instruction budget exceeded`;
    default:
      return t`Unavailable`;
  }
}

export function reasonLabel(reason: SkillRevocationReason) {
  switch (reason) {
    case "owner_revoked":
      return t`Owner decision`;
    case "regression":
      return t`Regression`;
    case "unsafe":
      return t`Unsafe instructions`;
    case "superseded":
      return t`Superseded version`;
  }
}
