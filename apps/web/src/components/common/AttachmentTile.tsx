import { Trans } from "@lingui/react/macro";
import type { Resource } from "../../lib/api";
import { artifactUrl } from "../../lib/artifacts";
export function AttachmentTile({
  artifact,
  onPreview,
}: {
  artifact: Resource;
  onPreview?: () => void;
}) {
  return (
    <div className="attachment">
      <span>▧</span>
      <div>
        <bdi>{String(artifact.payload.filename ?? artifact.payload.name ?? artifact.id)}</bdi>
        <small>
          {Number(artifact.payload.size ?? 0).toLocaleString()} <Trans>bytes</Trans>
        </small>
      </div>
      {onPreview && (
        <button type="button" onClick={onPreview}>
          <Trans>Preview</Trans>
        </button>
      )}
      <a className="button" href={artifactUrl(artifact.id)}>
        <Trans>Download</Trans>
      </a>
    </div>
  );
}
