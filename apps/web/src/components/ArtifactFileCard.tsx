import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import type { Resource } from "../lib/api";
import { artifactUrl } from "../lib/artifacts";
import "./artifact-file-card.css";

const imageTypes = new Set([
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "image/avif",
  "image/svg+xml",
]);

export function ArtifactFileCard({
  artifact,
  onPreview,
}: {
  artifact: Resource;
  onPreview?: () => void;
}) {
  const name = String(artifact.payload.filename ?? artifact.payload.name ?? artifact.id);
  const mime = String(
    artifact.payload.media_type ?? artifact.payload.mime_type ?? "",
  ).toLowerCase();
  const [failedId, setFailedId] = useState<string | null>(null);
  const image = imageTypes.has(mime) && failedId !== artifact.id;
  return (
    <div className="artifact-file-card" data-artifact-id={artifact.id}>
      {image && (
        <button
          type="button"
          className="artifact-image-preview"
          aria-label={t`Preview ${name}`}
          onClick={onPreview}
          disabled={!onPreview}
        >
          {/* SVG is loaded in the browser's image context, never as active inline markup. */}
          <img
            src={artifactUrl(artifact.id, true)}
            alt={name}
            loading="lazy"
            decoding="async"
            onError={() => setFailedId(artifact.id)}
          />
        </button>
      )}
      <div className="attachment">
        {!image && <span aria-hidden="true">▧</span>}
        <div>
          <bdi>{name}</bdi>
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
    </div>
  );
}
