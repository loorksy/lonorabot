import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { useEffect, useState } from "react";
import { api, isRequestCancelled } from "../lib/api";

/* «يتوفر إصدار جديد»: the served build id (GET /api/version, written next to the SPA at build
   time) is compared with this bundle's own id on the event stream's ready, on visibility and on
   the revision tick; the bar shows only when they differ. */
export function UpdateBar({ revision, forced = false }: { revision: number; forced?: boolean }) {
  const [served, setServed] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  useEffect(() => {
    void revision;
    let live = true;
    api
      .get<{ version: string; build: string | null }>("/version")
      .then((data) => {
        if (live) setServed(data.build);
      })
      .catch((failure) => {
        if (!isRequestCancelled(failure)) return;
      });
    return () => {
      live = false;
    };
  }, [revision]);
  const newer = forced ? "lab" : served;
  if (!newer || newer === __LONORA_BUILD__ || dismissed === newer) return null;
  return (
    <div id="update-bar" role="status">
      <span className="ub-ic">
        <Icon name="download" />
      </span>
      <span className="ub-t">
        <strong>
          <Trans>A new version is available</Trans>
        </strong>
        <small>
          <Trans>Update to get the latest improvements.</Trans>
        </small>
      </span>
      <button type="button" className="btn primary small" onClick={() => location.reload()}>
        <Trans>Update</Trans>
      </button>
      <button
        type="button"
        className="icon"
        aria-label={t`Later`}
        onClick={() => setDismissed(newer)}
      >
        <Icon name="close" />
      </button>
    </div>
  );
}
