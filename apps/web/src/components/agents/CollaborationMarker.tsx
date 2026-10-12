import { Trans } from "@lingui/react/macro";
import type { Run } from "../../lib/api";
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
