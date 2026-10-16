import { t } from "@lingui/core/macro";
import { Star } from "lucide-react";
import type { Agent } from "../../lib/api";

export function PersonalAgentBadge({ agent }: { agent?: Agent }) {
  if (agent?.role !== "personal") return null;
  return (
    <span
      role="img"
      aria-label={t`Personal Agent`}
      title={t`Personal Agent`}
      style={{
        color: "#b8860b",
        display: "inline-flex",
        marginInlineStart: 6,
        verticalAlign: "middle",
        flexShrink: 0,
      }}
    >
      <Star size={15} fill="currentColor" aria-hidden="true" />
    </span>
  );
}
