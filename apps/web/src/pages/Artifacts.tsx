import { Trans } from "@lingui/react/macro";
import { useEffect, useRef, useState } from "react";
import { AttachmentTile } from "../components/common/AttachmentTile";
import { FilePreviewPanel } from "../components/common/FilePreviewPanel";
import { api, type Resource } from "../lib/api";
import { artifacts } from "../lib/artifacts";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
export function Artifacts() {
  const { revision, refresh } = useClient();
  const [rows, setRows] = useState<Resource[]>([]);
  const [preview, setPreview] = useState<Resource | null>(null);
  const [error, setError] = useState<unknown>();
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    void artifacts.list().then(setRows).catch(setError);
  }, [revision]);
  return (
    <section>
      <div className="page-header">
        <h1>
          <Trans>Artifacts</Trans>
        </h1>
        <button type="button" onClick={() => input.current?.click()}>
          <Trans>Upload file</Trans>
        </button>
        <input
          ref={input}
          type="file"
          hidden
          multiple
          onChange={async (e) => {
            try {
              await Promise.all(Array.from(e.target.files ?? []).map((f) => api.upload(f)));
              refresh();
            } catch (err) {
              setError(err);
            }
            e.target.value = "";
          }}
        />
      </div>
      {error != null && <p role="alert">{userError(error)}</p>}
      {!rows.length && (
        <p className="empty">
          <Trans>Files and outputs from your agents will appear here.</Trans>
        </p>
      )}
      {rows.map((a) => (
        <AttachmentTile key={a.id} artifact={a} onPreview={() => setPreview(a)} />
      ))}
      {preview && <FilePreviewPanel artifact={preview} onClose={() => setPreview(null)} />}
    </section>
  );
}
