import { Trans } from "@lingui/react/macro";
import type { Run } from "../../lib/api";
export function WorkingIndicator({ run }: { run?: Run }) {
  if (!run) return null;
  const active = ["queued", "leased", "running"].includes(run.status);
  return (
    <span className={`working ${active ? "active" : ""}`} role="status">
      {run.status === "queued" ? (
        <Trans>Queued</Trans>
      ) : run.status === "leased" || run.status === "running" ? (
        <Trans>Working</Trans>
      ) : run.status === "waiting_input" ? (
        <Trans>Waiting for your reply</Trans>
      ) : run.status === "waiting_takeover" ? (
        <Trans>Waiting for handover</Trans>
      ) : run.status === "failed" ? (
        <Trans>Failed</Trans>
      ) : run.status === "cancelled" ? (
        <Trans>Cancelled</Trans>
      ) : (
        <Trans>Completed</Trans>
      )}
    </span>
  );
}
