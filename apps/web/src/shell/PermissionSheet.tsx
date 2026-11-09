import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon, type IconName } from "@lonora/ui-web";
import { useCallback } from "react";
import { useSheets } from "./sheets/SheetHost";

/* Permissions the browser refused: a bar sheet with the hero icon, the reason and the steps to
   allow it again. Microphone and camera only (Q10): notifications wait for a push channel. */
export type PermissionKind = "mic" | "camera";

function PermissionBody({ kind, onDone }: { kind: PermissionKind; onDone: () => void }) {
  const icon: IconName = kind === "mic" ? "mic" : "camera";
  return (
    <>
      <div className="state-hero">
        <Icon name={icon} />
        <i className="state-x">
          <Icon name="close" />
        </i>
      </div>
      <p className="state-lead">
        {kind === "mic" ? (
          <Trans>
            Lonora needs the microphone for dictation, voice messages and calls. Nothing is recorded
            without your tap.
          </Trans>
        ) : (
          <Trans>Lonora needs the camera to take photos and send them in the chat.</Trans>
        )}
      </p>
      <ol className="perm-steps">
        <li>
          <Trans>Tap the lock icon next to the site address.</Trans>
        </li>
        <li>
          {kind === "mic" ? (
            <Trans>Open “Permissions”, then “Microphone”.</Trans>
          ) : (
            <Trans>Open “Permissions”, then “Camera”.</Trans>
          )}
        </li>
        <li>
          <Trans>Choose “Allow”, then come back and try again.</Trans>
        </li>
      </ol>
      <div className="actions">
        <button type="button" className="btn primary" onClick={onDone}>
          <Trans>OK</Trans>
        </button>
      </div>
    </>
  );
}

export function usePermissionSheet() {
  const sheets = useSheets();
  return useCallback(
    (kind: PermissionKind) => {
      const title = kind === "mic" ? t`Microphone not allowed` : t`Camera not allowed`;
      sheets.open({
        id: "perm",
        bar: true,
        title,
        label: title,
        body: <PermissionBody kind={kind} onDone={() => sheets.close()} />,
      });
    },
    [sheets],
  );
}
