import { useLingui } from "@lingui/react";
import {
  type AccountAuthority,
  type Agent,
  type AuthorityAction,
  authorityActions,
  type DeviceChallenge,
  type Resource,
  type Thread,
} from "@lonora/contracts";
import {
  accountAuthorityLabels,
  activateAccountAuthority,
  authorityLimitFields,
  authorityProposal,
  authorityStatus,
  emptyAuthorityDraft,
  webDeviceProof,
  webDeviceSupported,
} from "@lonora/core";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, isRequestCancelled } from "../../lib/api";
import { brokerIdentityLabel } from "../../lib/broker-identity";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { type BrokerPair, BrokerPairPicker } from "./BrokerPairPicker";

/** Owner-controlled settings. No Agent message or local toggle activates permission. */
export function AccountAuthoritySettings({ agent }: { agent: Agent }) {
  const { i18n } = useLingui();
  const text = accountAuthorityLabels[i18n.locale.startsWith("ar") ? "ar" : "en"];
  const { owner, revision } = useClient();
  const [rows, setRows] = useState<AccountAuthority[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [connections, setConnections] = useState<Resource[]>([]);
  const [draft, setDraft] = useState(emptyAuthorityDraft);
  const [pair, setPair] = useState<BrokerPair>({
    trading_account_id: agent.trading_account_id ?? "",
    trading_symbol: agent.trading_symbol ?? "",
  });
  const [symbols, setSymbols] = useState<string[]>(
    agent.trading_symbol ? [agent.trading_symbol] : [],
  );
  const [actions, setActions] = useState<AuthorityAction[]>([]);
  const [threadId, setThreadId] = useState("");
  const [manual, setManual] = useState(false);
  const [open, setOpen] = useState(false);
  const [review, setReview] = useState<AccountAuthority | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [password, setPassword] = useState("");
  const [enroll, setEnroll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [tick, setTick] = useState(0);
  const scope = `${owner.id}:${agent.id}`;
  const currentScope = useRef(scope);
  currentScope.current = scope;
  useEffect(() => {
    void revision;
    void tick;
    let active = true;
    setError(undefined);
    void Promise.all([
      api.get<AccountAuthority[]>(`/agents/${encodeURIComponent(agent.id)}/account-authorities`),
      api.get<Thread[]>(`/threads?agent_id=${encodeURIComponent(agent.id)}`),
      api.get<Resource[]>("/trading/connections"),
    ])
      .then(([saved, conversations, accounts]) => {
        if (!active) return;
        setRows(saved.filter((row) => row.agent_id === agent.id));
        setThreads(conversations.filter((row) => row.agent_id === agent.id && !row.group_id));
        setConnections(accounts);
      })
      .catch((cause) => {
        if (active && !isRequestCancelled(cause)) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [agent.id, revision, tick]);
  const execute = async (operation: () => Promise<void>) => {
    if (busy) return;
    const started = scope;
    setBusy(true);
    setError(undefined);
    try {
      await operation();
    } catch (cause) {
      if (currentScope.current === started && !isRequestCancelled(cause)) {
        setError(cause);
        if (cause instanceof ApiError && cause.code === "device_registration_required")
          setEnroll(true);
      }
    } finally {
      if (currentScope.current === started) {
        setBusy(false);
        setTick((value) => value + 1);
      }
    }
  };
  const proposal = authorityProposal(draft, {
    thread_id: threadId || (threads.length === 1 ? threads[0].id : ""),
    account_id: pair.trading_account_id,
    symbols,
    actions,
    allow_manual_positions: manual,
  });
  const accountName = (id: string) => {
    const index = connections.findIndex((row) => row.id === id);
    return index >= 0 ? brokerIdentityLabel(connections[index], index) : text.account;
  };
  const supported = webDeviceSupported();
  if (agent.role === "delegated") return null;
  return (
    <details
      className="tpl-profile-advanced"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        {text.title} ·{" "}
        {rows.some((row) => authorityStatus(row) === "active") ? text.active : text.off}
      </summary>
      {open && (
        <fieldset disabled={busy}>
          <p className="muted">{text.hint}</p>
          <p>{text.limitsUnavailable}</p>
          {rows.map((row) => (
            <section key={row.id} aria-label={text.title}>
              <p>
                {text[authorityStatus(row)]} · {accountName(row.account_id)} ·{" "}
                <bdi>{row.envelope.symbols.join(", ")}</bdi>
              </p>
              <p>
                <time dateTime={row.valid_until}>
                  {new Date(row.valid_until).toLocaleString(i18n.locale)}
                </time>
              </p>
              {authorityStatus(row) === "pending" && (
                <button
                  type="button"
                  onClick={() => {
                    setReview(row);
                    setAcknowledged(false);
                    setEnroll(false);
                  }}
                >
                  {text.review}
                </button>
              )}
              {["active", "pending"].includes(authorityStatus(row)) && (
                <button
                  type="button"
                  onClick={() =>
                    void execute(async () => {
                      await api.post(
                        `/account-authorities/${encodeURIComponent(row.id)}/revoke`,
                        {},
                      );
                    })
                  }
                >
                  {text.revoke}
                </button>
              )}
            </section>
          ))}
          {review && (
            <section aria-label={text.review}>
              <h4>{text.review}</h4>
              <p>
                {accountName(review.account_id)} · <bdi>{review.envelope.symbols.join(", ")}</bdi>
              </p>
              <p>{review.envelope.actions.map((action) => text[action]).join(" · ")}</p>
              {authorityLimitFields.map((field) => (
                <p key={field}>
                  {text[field]}: <bdi>{String(review.envelope[field])}</bdi>
                </p>
              ))}
              <p>
                {text.manual}: {review.envelope.allow_manual_positions ? "✓" : "—"}
              </p>
              <label className="check">
                <input
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                />
                {text.acknowledge}
              </label>
              {!supported && <p>{text.unsupported}</p>}
              <button
                type="button"
                disabled={!supported || !acknowledged || authorityStatus(review) !== "pending"}
                onClick={() =>
                  void execute(async () => {
                    const updated = await activateAccountAuthority(api, review, webDeviceProof);
                    if (currentScope.current === scope) {
                      setRows((value) =>
                        value.map((row) => (row.id === updated.id ? updated : row)),
                      );
                      setReview(null);
                    }
                  })
                }
              >
                {text.review}
              </button>
              {enroll && (
                <section>
                  <label>
                    {text.password}
                    <input
                      type="password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    disabled={!password || !supported}
                    onClick={() =>
                      void execute(async () => {
                        const secret = password;
                        setPassword("");
                        const challenge = await api.post<DeviceChallenge>(
                          "/auth/devices/enrollment",
                          { password: secret, name: text.device },
                        );
                        await api.post(
                          "/auth/devices/enrollment/verify",
                          await webDeviceProof(challenge, true),
                        );
                        if (currentScope.current === scope) setEnroll(false);
                      })
                    }
                  >
                    {text.register}
                  </button>
                </section>
              )}
              <button
                type="button"
                onClick={() => {
                  setReview(null);
                  setPassword("");
                  setEnroll(false);
                }}
              >
                {text.close}
              </button>
            </section>
          )}
          <details>
            <summary>{text.create}</summary>
            {!threads.length && <p>{text.noThread}</p>}
            {threads.length > 1 && (
              <label>
                {text.thread}
                <select value={threadId} onChange={(event) => setThreadId(event.target.value)}>
                  <option value="">—</option>
                  {threads.map((thread) => (
                    <option key={thread.id} value={thread.id}>
                      {thread.title || text.thread}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {agent.trading_symbol ? (
              <p>
                {accountName(pair.trading_account_id)} · <bdi>{agent.trading_symbol}</bdi>
              </p>
            ) : (
              <>
                <BrokerPairPicker
                  value={pair}
                  onChange={(next) => {
                    if (next.trading_account_id !== pair.trading_account_id) setSymbols([]);
                    setPair(next);
                  }}
                />
                <button
                  type="button"
                  disabled={
                    !pair.trading_symbol ||
                    symbols.includes(pair.trading_symbol) ||
                    symbols.length >= 100
                  }
                  onClick={() => setSymbols((value) => [...value, pair.trading_symbol])}
                >
                  {text.add}
                </button>
                <p>
                  {symbols.map((symbol) => (
                    <button
                      type="button"
                      key={symbol}
                      onClick={() => setSymbols((value) => value.filter((item) => item !== symbol))}
                    >
                      {symbol} ×
                    </button>
                  ))}
                </p>
              </>
            )}
            <fieldset>
              <legend>{text.actions}</legend>
              {authorityActions.map((action) => (
                <label className="check" key={action}>
                  <input
                    type="checkbox"
                    checked={actions.includes(action)}
                    onChange={(event) =>
                      setActions((value) =>
                        event.target.checked
                          ? [...value, action]
                          : value.filter((item) => item !== action),
                      )
                    }
                  />
                  {text[action]}
                </label>
              ))}
            </fieldset>
            {authorityLimitFields.map((field) => (
              <label key={field}>
                {text[field]}
                <input
                  type="text"
                  inputMode={field === "valid_until" ? "text" : "decimal"}
                  value={draft[field]}
                  onChange={(event) =>
                    setDraft((value) => ({ ...value, [field]: event.target.value }))
                  }
                />
              </label>
            ))}
            <label className="check">
              <input
                type="checkbox"
                checked={manual}
                onChange={(event) => setManual(event.target.checked)}
              />
              {text.manual}
            </label>
            <button
              type="button"
              disabled={!proposal || agent.execution_mode === "shadow" || agent.paused}
              onClick={() =>
                void execute(async () => {
                  if (!proposal) return;
                  const row = await api.post<AccountAuthority>(
                    `/agents/${encodeURIComponent(agent.id)}/account-authorities`,
                    proposal,
                  );
                  if (currentScope.current === scope) {
                    setReview(row);
                    setAcknowledged(false);
                    setRows((value) => [
                      row,
                      ...value.filter((existing) => existing.id !== row.id),
                    ]);
                  }
                })
              }
            >
              {text.save}
            </button>
          </details>
          {error != null && <p role="alert">{userError(error)}</p>}
        </fieldset>
      )}
    </details>
  );
}
