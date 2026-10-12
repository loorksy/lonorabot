import { Trans } from "@lingui/react/macro";
import type { Event } from "../../lib/api";
export function RecoveryNotice({ events }: { events: Event[] }) {
  return events.some((e) => e.kind.includes("recover")) ? (
    <p className="notice">
      <Trans>The task resumed from its saved state after reconnection.</Trans>
    </p>
  ) : null;
}
