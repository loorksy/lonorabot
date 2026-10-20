import type { SkillRevocationReason } from "@lonora/contracts";
import { StyleSheet } from "react-native";
import type { Label } from "../../lib/i18n";
import { colors } from "../ui";

export const reasons: { id: SkillRevocationReason; label: Label }[] = [
  { id: "owner_revoked", label: "skillsReasonOwner" },
  { id: "regression", label: "skillsReasonRegression" },
  { id: "unsafe", label: "skillsReasonUnsafe" },
  { id: "superseded", label: "skillsReasonSuperseded" },
];
export const semanticVersion = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;

export function availabilityLabel(code: string, t: (label: Label) => string) {
  const labels: Record<string, Label> = {
    skill_version_revoked: "skill_version_revoked",
    skill_disabled: "skill_disabled",
    skill_dependency_unavailable: "skill_dependency_unavailable",
    skill_required_tools_unavailable: "skill_required_tools_unavailable",
    skill_required_capability_unavailable: "skill_required_capability_unavailable",
    skill_context_budget_exceeded: "skill_context_budget_exceeded",
    skill_total_budget_exceeded: "skill_total_budget_exceeded",
    skill_manifest_invalid: "skill_manifest_invalid",
    skill_builtin_override_denied: "skill_builtin_override_denied",
    skill_reference_missing: "skill_reference_missing",
    skill_dependency_cycle: "skill_dependency_cycle",
  };
  return t(labels[code] ?? "skillsUnavailable");
}

export const styles = StyleSheet.create({
  page: { padding: 20, gap: 16, paddingBottom: 40 },
  row: { alignItems: "center", gap: 10 },
  card: { backgroundColor: colors.muted, borderRadius: 18, padding: 17, gap: 10 },
  heading: { color: colors.foreground, fontSize: 17, fontWeight: "600" },
  hint: { color: colors.secondary, fontSize: 14, lineHeight: 21 },
  caption: { color: colors.foreground, fontSize: 13, lineHeight: 20 },
  technical: { color: colors.secondary, fontSize: 13, writingDirection: "ltr", textAlign: "left" },
  instructions: { color: colors.foreground, fontSize: 15, lineHeight: 23 },
  option: { padding: 12, borderRadius: 11, borderWidth: 1, borderColor: colors.border },
});
