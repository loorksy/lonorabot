import {
  type AccountAuthority,
  type Agent,
  type AuthorityDuration,
  authorityActions,
  type PermissionCustomization,
  type Resource,
} from "@lonora/contracts";
import { type accountAuthorityLabels, numericalAuthorityLimits } from "@lonora/core";
import { useState } from "react";
import { brokerIdentityLabel } from "../../lib/broker-identity";
import type { PermissionText } from "./permission-labels";

export function permissionAccountName(accounts: Resource[], id: string, fallback: string) {
  const index = accounts.findIndex((account) => account.id === id);
  return index < 0 ? fallback : brokerIdentityLabel(accounts[index], index);
}

type Labels = (typeof accountAuthorityLabels)[keyof typeof accountAuthorityLabels];
export function PermissionSummary({
  agentName,
  value,
  accounts,
  currency,
  text,
  labels,
  locale,
  exact = false,
}: {
  agentName: string;
  value: PermissionCustomization | AccountAuthority["envelope"];
  accounts: Resource[];
  currency: string;
  text: PermissionText;
  labels: Labels;
  locale: string;
  exact?: boolean;
}) {
  const draft = "limits" in value ? value : null;
  const validUntil = "valid_until" in value ? value.valid_until : null;
  return (
    <section className="permission-summary" aria-label={text.summary}>
      <h3>{text.summary}</h3>
      <p data-testid="permission-summary-agent">
        <strong>
          <bdi>{agentName}</bdi>
        </strong>
      </p>
      <p className="permission-account">
        <bdi>{permissionAccountName(accounts, value.account_id, labels.account)}</bdi>
      </p>
      <p>
        <bdi>
          {value.symbol_scope === "account" ? text.accountWide : value.symbols.join(" · ") || "—"}
        </bdi>
      </p>
      <div className="permission-summary-actions">
        {value.actions.map((action) => (
          <span key={action}>{labels[action]}</span>
        ))}
      </div>
      <dl>
        {numericalAuthorityLimits.map((field) => {
          const limit = draft
            ? draft.limits[field]
            : (value as AccountAuthority["envelope"])[field];
          return (
            <div key={field}>
              <dt>
                {labels[field]}
                {field === "minimum_equity" && currency ? ` · ${currency}` : ""}
              </dt>
              <dd>
                <bdi>{limit === null || limit === "" ? text.unlimited : String(limit)}</bdi>
              </dd>
            </div>
          );
        })}
        <div>
          <dt>{text.duration}</dt>
          <dd>
            {draft ? (
              text[draft.duration]
            ) : validUntil ? (
              <time dateTime={validUntil}>
                {new Date(validUntil).toLocaleString(locale, { timeZoneName: "short" })}
              </time>
            ) : (
              text.until_stopped
            )}
          </dd>
        </div>
        <div>
          <dt>{labels.manual}</dt>
          <dd>{value.allow_manual_positions ? text.included : text.excluded}</dd>
        </div>
      </dl>
      {exact && <p className="permission-explanation">{text.noApproval}</p>}
      <p className="permission-explanation">{text.risk}</p>
    </section>
  );
}

/** Editing preferences never grants authority. Every review is a fresh server proposal. */
export function PermissionEditor({
  agent,
  draft,
  onChange,
  accounts,
  symbols,
  currency,
  text,
  labels,
  symbolError,
}: {
  agent: Agent;
  draft: PermissionCustomization;
  onChange: (value: PermissionCustomization) => void;
  accounts: Resource[];
  symbols: string[];
  currency: string;
  text: PermissionText;
  labels: Labels;
  symbolError?: string;
}) {
  const [market, setMarket] = useState("");
  const bound = Boolean(agent.trading_account_id && agent.trading_symbol);
  return (
    <div className="permission-groups">
      <details data-testid="permission-group-scope">
        <summary>{text.scope}</summary>
        <div className="permission-group-body">
          {bound ? (
            <p className="permission-fixed-scope">
              <bdi>
                {permissionAccountName(accounts, agent.trading_account_id ?? "", labels.account)}
              </bdi>
              <bdi>{agent.trading_symbol}</bdi>
            </p>
          ) : (
            <>
              <label>
                {text.chooseAccount}
                <select
                  data-testid="permission-account"
                  value={draft.account_id}
                  onChange={(event) => {
                    setMarket("");
                    onChange({ ...draft, account_id: event.target.value, symbols: [] });
                  }}
                >
                  <option value="">—</option>
                  {accounts
                    .filter((account) => account.payload.enabled !== false)
                    .map((account) => (
                      <option key={account.id} value={account.id}>
                        {permissionAccountName(accounts, account.id, labels.account)}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                {labels.symbols}
                <select
                  data-testid="permission-symbol-scope"
                  value={draft.symbol_scope}
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      symbol_scope: event.target.value as "selected" | "account",
                      symbols: [],
                    })
                  }
                >
                  <option value="selected">{text.selectedMarkets}</option>
                  <option value="account">{text.accountWide}</option>
                </select>
              </label>
              {draft.symbol_scope === "selected" && (
                <>
                  <label>
                    {text.chooseMarket}
                    <select
                      value={market}
                      disabled={!draft.account_id}
                      onChange={(event) => setMarket(event.target.value)}
                    >
                      <option value="">—</option>
                      {symbols
                        .filter((symbol) => !draft.symbols.includes(symbol))
                        .map((symbol) => (
                          <option key={symbol} value={symbol}>
                            {symbol}
                          </option>
                        ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    disabled={!market}
                    onClick={() => {
                      onChange({ ...draft, symbols: [...draft.symbols, market] });
                      setMarket("");
                    }}
                  >
                    {text.addMarket}
                  </button>
                  <div className="permission-markets">
                    {draft.symbols.map((symbol) => (
                      <button
                        type="button"
                        key={symbol}
                        aria-label={`${text.removeMarket}: ${symbol}`}
                        onClick={() =>
                          onChange({
                            ...draft,
                            symbols: draft.symbols.filter((item) => item !== symbol),
                          })
                        }
                      >
                        <bdi>{symbol}</bdi> ×
                      </button>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
          {symbolError && <p role="alert">{symbolError}</p>}
        </div>
      </details>
      <details data-testid="permission-group-actions">
        <summary>
          {text.actions}
          <span>
            {draft.actions.length}/{authorityActions.length}
          </span>
        </summary>
        <div className="permission-group-body">
          <div className="permission-inline-buttons">
            <button
              type="button"
              data-testid="permission-select-all"
              onClick={() => onChange({ ...draft, actions: [...authorityActions] })}
            >
              {text.selectAll}
            </button>
            <button
              type="button"
              data-testid="permission-deselect-all"
              onClick={() => onChange({ ...draft, actions: [] })}
            >
              {text.deselectAll}
            </button>
          </div>
          <div className="permission-action-grid">
            {authorityActions.map((action) => (
              <label className="permission-checkbox" key={action}>
                <input
                  data-testid={`permission-action-${action}`}
                  type="checkbox"
                  role="switch"
                  data-lonora-switch="true"
                  aria-checked={draft.actions.includes(action)}
                  checked={draft.actions.includes(action)}
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      actions: event.target.checked
                        ? [...draft.actions, action]
                        : draft.actions.filter((item) => item !== action),
                    })
                  }
                />
                {labels[action]}
              </label>
            ))}
          </div>
        </div>
      </details>
      <details data-testid="permission-group-limits">
        <summary>
          {text.limits}
          <span>
            {Object.values(draft.limits).filter((value) => value.trim()).length || text.optional}
          </span>
        </summary>
        <div className="permission-group-body permission-limit-grid">
          {numericalAuthorityLimits.map((field) => (
            <label key={field} htmlFor={`permission-limit-${field}`}>
              {labels[field]}
              {field === "minimum_equity" && <small>{currency || text.accountCurrency}</small>}
              <input
                id={`permission-limit-${field}`}
                data-testid={`permission-limit-${field}`}
                inputMode={
                  field.includes("volume") || field === "minimum_equity" ? "decimal" : "numeric"
                }
                autoComplete="off"
                maxLength={80}
                placeholder={text.unlimited}
                value={draft.limits[field]}
                onChange={(event) =>
                  onChange({ ...draft, limits: { ...draft.limits, [field]: event.target.value } })
                }
              />
            </label>
          ))}
          <p className="permission-explanation permission-span-all">{text.equityExplanation}</p>
        </div>
      </details>
      <details data-testid="permission-group-duration">
        <summary>{text.duration}</summary>
        <div className="permission-group-body">
          <label>
            {text.duration}
            <select
              data-testid="permission-duration"
              value={draft.duration}
              onChange={(event) =>
                onChange({ ...draft, duration: event.target.value as AuthorityDuration })
              }
            >
              {(["until_stopped", "12h", "24h", "7d"] as const).map((duration) => (
                <option key={duration} value={duration}>
                  {text[duration]}
                </option>
              ))}
            </select>
          </label>
          <label className="permission-checkbox">
            <input
              data-testid="permission-manual"
              type="checkbox"
              role="switch"
              data-lonora-switch="true"
              aria-checked={draft.allow_manual_positions}
              checked={draft.allow_manual_positions}
              onChange={(event) =>
                onChange({ ...draft, allow_manual_positions: event.target.checked })
              }
            />
            {labels.manual}
          </label>
        </div>
      </details>
    </div>
  );
}
