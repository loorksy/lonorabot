import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { api, type Payload } from "../lib/api";
import { userError } from "../lib/user_error";
export function VoiceSettingsOverlay() {
  const [status, setStatus] = useState<Payload>();
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void api.get<Payload>("/voice/status").then(setStatus).catch(setError);
  }, []);
  return (
    <section className="card">
      <h2>
        <Trans>Realtime conversation</Trans>
      </h2>
      <p>
        <Trans>
          Speech becomes a message in the current conversation. The same agent answers and uses its
          normal tools.
        </Trans>
      </p>
      <p className="muted">
        <Trans>
          Set speech recognition and speech synthesis under global model routing. Configure LiveKit
          on the server to enable calls.
        </Trans>
      </p>
      {status && (
        <p role="status">
          {status.transport_configured ? (
            <Trans>Voice transport configured</Trans>
          ) : (
            <Trans>Voice transport needs configuration</Trans>
          )}
        </p>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}
