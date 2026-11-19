import { t } from "@lingui/core/macro";
import { Icon } from "@lonora/ui-web";
import type { CSSProperties } from "react";

/* An upload's progress ring with its cancel (reference uploadMarkup, Desktop-37 5530-5533):
   in the composer's tray while the file uploads, and in the bubble once the message is
   sent. The reference hides the number; here the ring carries it for a screen reader. */
export function UploadRing({
  name,
  p,
  onCancel,
}: {
  name: string;
  p: number;
  onCancel: () => void;
}) {
  return (
    <span className="up" style={{ "--p": p } as CSSProperties}>
      <span
        className="up-ring"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(p * 100)}
        aria-label={t`Uploading ${name}`}
      />
      <button type="button" className="up-x" aria-label={t`Cancel the upload`} onClick={onCancel}>
        <Icon name="close" />
      </button>
    </span>
  );
}
