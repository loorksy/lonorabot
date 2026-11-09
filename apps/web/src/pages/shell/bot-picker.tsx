// Adapted for Lonora from Tampletgrok pages/shell/bot-picker.tsx; Apache-2.0.

import { t } from "@lingui/core/macro";
import type { Agent } from "../../lib/api";

export function AgentPicker({
  agents,
  value,
  onChange,
}: {
  agents: Agent[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <select aria-label={t`Agent`} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t`Choose an agent`}</option>
      {agents.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name}
        </option>
      ))}
    </select>
  );
}
