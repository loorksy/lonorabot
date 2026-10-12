import { Trans, useLingui } from "@lingui/react/macro";
import { Download, X } from "lucide-react";
import { Component, type ReactNode, useEffect, useId, useRef } from "react";
import { useOverlayHistory } from "../../hooks/useOverlayHistory";
import type { Resource } from "../../lib/api";
import { artifactUrl } from "../../lib/artifacts";
import { ImageGallery } from "./ImageGallery";
import { PdfViewer } from "./PdfViewer";
import { SandboxedHtmlViewer } from "./SandboxedHtmlViewer";

class PreviewBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="workspace-empty" role="alert">
        <p>
          <Trans>The file preview could not be displayed</Trans>
        </p>
        <p>
          <Trans>Download this file to view it</Trans>
        </p>
      </div>
    ) : (
      this.props.children
    );
  }
}

export function FilePreviewPanel({
  artifact,
  onClose,
  historyManaged = true,
}: {
  artifact: Resource;
  onClose: () => void;
  historyManaged?: boolean;
}) {
  const { t } = useLingui();
  const titleId = useId();
  const dialog = useRef<HTMLElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const mime = String(artifact.payload.media_type ?? artifact.payload.mime_type ?? "");
  const name = String(artifact.payload.filename ?? artifact.payload.name ?? artifact.id);
  const url = artifactUrl(artifact.id, true);
  useOverlayHistory(historyManaged, onClose);
  useEffect(() => {
    const previous = document.activeElement;
    close.current?.focus();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, []);

  return (
    <div className="workspace-dialog-backdrop workspace-preview-backdrop">
      <section
        ref={dialog}
        className="workspace-dialog workspace-file-preview"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={(event) => {
          if (event.key === "Escape" && !historyManaged) {
            event.preventDefault();
            onClose();
            return;
          }
          if (event.key !== "Tab") return;
          const controls = dialog.current?.querySelectorAll<HTMLElement>(
            "button:not(:disabled),a[href],iframe",
          );
          const first = controls?.[0];
          const last = controls?.[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <header className="workspace-dialog-header">
          <h2 id={titleId}>
            <bdi>{name}</bdi>
          </h2>
          <div className="workspace-surface-actions">
            <a className="workspace-button" href={artifactUrl(artifact.id)}>
              <Download size={15} aria-hidden="true" />
              <Trans>Download</Trans>
            </a>
            <button
              ref={close}
              type="button"
              className="workspace-icon-button"
              aria-label={t`Close`}
              onClick={onClose}
            >
              <X size={19} aria-hidden="true" />
            </button>
          </div>
        </header>
        <div className="workspace-file-preview-body">
          <PreviewBoundary key={artifact.id}>
            {mime.startsWith("image/") && mime !== "image/svg+xml" ? (
              <ImageGallery url={url} name={name} />
            ) : mime === "application/pdf" ? (
              <PdfViewer url={url} />
            ) : mime === "text/html" || mime === "image/svg+xml" ? (
              <SandboxedHtmlViewer url={url} />
            ) : (
              <div className="workspace-empty">
                <p>
                  <Trans>Download this file to view it</Trans>
                </p>
              </div>
            )}
          </PreviewBoundary>
        </div>
      </section>
    </div>
  );
}
