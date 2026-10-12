import { Trans } from "@lingui/react/macro";
import type { Resource } from "../../lib/api";
import { artifactUrl } from "../../lib/artifacts";
import { ImageGallery } from "./ImageGallery";
import { PdfViewer } from "./PdfViewer";
import { SandboxedHtmlViewer } from "./SandboxedHtmlViewer";
export function FilePreviewPanel({
  artifact,
  onClose,
}: {
  artifact: Resource;
  onClose: () => void;
}) {
  const mime = String(artifact.payload.media_type ?? artifact.payload.mime_type ?? "");
  const url = `${artifactUrl(artifact.id)}?preview=true`;
  return (
    <div className="modal-backdrop">
      <section className="modal wide">
        <div className="row">
          <h2>
            <bdi>{String(artifact.payload.filename ?? artifact.payload.name ?? "")}</bdi>
          </h2>
          <button type="button" onClick={onClose}>
            <Trans>Close</Trans>
          </button>
        </div>
        {mime.startsWith("image/") && mime !== "image/svg+xml" ? (
          <ImageGallery url={url} name={String(artifact.payload.filename ?? "")} />
        ) : mime === "application/pdf" ? (
          <PdfViewer url={url} />
        ) : mime === "text/html" || mime === "image/svg+xml" ? (
          <SandboxedHtmlViewer url={url} />
        ) : (
          <p>
            <a href={artifactUrl(artifact.id)}>
              <Trans>Download this file to view it</Trans>
            </a>
          </p>
        )}
      </section>
    </div>
  );
}
