import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
export function UsageSettingsPanel() {
  const [usage, setUsage] = useState<{
    input_tokens: number;
    output_tokens: number;
    cached_tokens: number;
  }>();
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void api.get<typeof usage>("/usage/summary").then(setUsage).catch(setError);
  }, []);
  return (
    <section className="card">
      <h2>
        <Trans>Token usage</Trans>
      </h2>
      {usage && (
        <dl className="stats">
          <div>
            <dt>
              <Trans>Input</Trans>
            </dt>
            <dd>{usage.input_tokens.toLocaleString()}</dd>
          </div>
          <div>
            <dt>
              <Trans>Output</Trans>
            </dt>
            <dd>{usage.output_tokens.toLocaleString()}</dd>
          </div>
          <div>
            <dt>
              <Trans>Cached</Trans>
            </dt>
            <dd>{usage.cached_tokens.toLocaleString()}</dd>
          </div>
        </dl>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}
