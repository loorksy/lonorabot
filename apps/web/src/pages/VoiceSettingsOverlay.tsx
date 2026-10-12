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
          Spoken tasks are saved in the current conversation. GPT-Live can keep listening and
          speaking while the same agent performs delegated work.
        </Trans>
      </p>
      <p className="muted">
        <Trans>
          GPT-Live connects directly over WebRTC using your server-stored OpenAI credential. Choose
          the voice model in global routing; delegated work uses the same Lonora agent and tools.
        </Trans>
      </p>
      {status && (
        <p role="status">
          {status.transport_configured ? (
            <Trans>OpenAI voice credential configured</Trans>
          ) : (
            <Trans>Configure an OpenAI credential with GPT-Live API access</Trans>
          )}
        </p>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}
