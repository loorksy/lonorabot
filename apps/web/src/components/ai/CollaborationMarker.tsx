import { Trans } from "@lingui/react/macro";
import type { Run } from "../../lib/api";
import { WorkingIndicator } from "./primitives";
export function CollaborationMarker({ run }: { run: Run }) {
  return run.parent_run_id ? (
    <span className="badge">
      <Trans>Delegated task</Trans>
    </span>
  ) : run.trigger === "peer" ? (
    <span className="badge">
      <Trans>Agent collaboration</Trans>
    </span>
  ) : null;
}

export function SubagentTasks({ runs }: { runs: Run[] }) {
  const children = runs.filter((r) => r.parent_run_id && r.trigger === "subagent");
  return children.length ? (
    <details>
      <summary>
        <Trans>Temporary delegated tasks</Trans> ({children.length})
      </summary>
      {children.map((r) => (
        <div className="row" key={r.id}>
          <code>{r.id.slice(0, 8)}</code>
          <WorkingIndicator run={r} />
        </div>
      ))}
    </details>
  ) : null;
}
