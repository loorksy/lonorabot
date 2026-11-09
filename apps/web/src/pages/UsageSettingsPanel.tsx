import { i18n } from "@lingui/core";
import { Trans } from "@lingui/react/macro";
import type { AgentUsageReport } from "@lonora/contracts";
import { agentModelText, modelName, usageLine } from "@lonora/core";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
export function UsageSettingsPanel() {
  const locale = i18n.locale;
  const text = agentModelText(locale);
  const [agents, setAgents] = useState<AgentUsageReport>();
  const [usage, setUsage] = useState<{
    input_tokens: number;
    output_tokens: number;
    cached_tokens: number;
  }>();
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void api.get<typeof usage>("/usage/summary").then(setUsage).catch(setError);
    void api.get<AgentUsageReport>("/usage/agents?days=30").then(setAgents).catch(setError);
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
      {agents && (
        <section aria-label={text.usageTitle} className="lonora-agent-usage">
          <h3>{text.usageTitle}</h3>
          <p className="muted">{text.usageHint}</p>
          {agents.agents.length === 0 ? (
            <p>
              {usageLine({ input_tokens: 0, output_tokens: 0, requests: 0 }, agents.days, locale)}
            </p>
          ) : (
            <ul>
              {agents.agents.map((item) => (
                <li key={item.agent_id ?? "none"} dir="auto">
                  <strong>
                    <bdi>{item.agent_name ?? text.unattributed}</bdi>
                  </strong>{" "}
                  · {usageLine(item, agents.days, locale)}
                  {item.models.length > 0 && (
                    <span className="muted">
                      {" "}
                      ·{" "}
                      {item.models
                        .slice(0, 3)
                        .map((model) => modelName({ ...model, name: null }))
                        .join(" · ")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}
