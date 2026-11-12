import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentModelSummary } from "@lonora/contracts";
import { Icon } from "@lonora/ui-web";
import { useEffect, useRef, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { type Agent, api, type Resource } from "../../lib/api";
import { readSymbols } from "../../lib/market";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { clearDirty, markDirty, useNavigation } from "../navigation";
import { SkPage, SkRows } from "../Skeleton";
import { NotFoundPage } from "../StatePage";
import { useToast } from "../Toast";
import { useAvatarSheet } from "./AvatarSheet";
import { accountLabel, isTrader, usePageAgent, useRead } from "./shared";
import "./agent.css";

const modelKey = (item: { provider: string; model: string }) => `${item.provider}:${item.model}`;

/* «الهوية والنموذج» (route identity): name, role, model and — for a trading agent — its
   account and pair from that account's symbols. Saving is PATCH /api/agents/{id} (a pair or
   account change is the server's scope change with its revision: it never signs, moves or
   widens a grant) and PUT /api/agents/{id}/model. */
export function IdentityPage({ agentId }: { agentId: string }) {
  const data = useShellData();
  const { agent, missing } = usePageAgent(agentId, data.agents, data.agentsLoading);
  if (!agent)
    return !missing ? (
      <SkPage>
        <SkRows count={4} />
      </SkPage>
    ) : (
      <NotFoundPage />
    );
  return <IdentityForm key={agent.id} agent={agent} />;
}

function IdentityForm({ agent }: { agent: Agent }) {
  const data = useShellData();
  const nav = useNavigation();
  const toast = useToast();
  const openAvatar = useAvatarSheet();
  const trader = isTrader(agent);
  const connections = useRead<Resource[]>(trader ? "/trading/connections" : null);
  const model = useRead<AgentModelSummary>(`/agents/${encodeURIComponent(agent.id)}/model/summary`);
  const [name, setName] = useState(agent.name);
  const [role, setRole] = useState(agent.description || agent.title || "");
  const [choice, setChoice] = useState<string | null>(null);
  const [account, setAccount] = useState(agent.trading_account_id ?? "");
  const [symbol, setSymbol] = useState(agent.trading_symbol ?? "");
  const [symbols, setSymbols] = useState<string[] | null>(null);
  // Only the owner's own pick changes the market: never a default, never a re-pick.
  const [marketEdited, setMarketEdited] = useState(false);
  const edited = useRef(false);
  edited.current = marketEdited;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [tried, setTried] = useState(false);
  const accounts = (connections.value ?? []).filter((row) => row.payload.enabled !== false);
  const savedModel =
    model.value?.record.mode === "fixed" && model.value.record.preference.primary
      ? modelKey(model.value.record.preference.primary)
      : "";
  const modelValue = choice ?? savedModel;
  useEffect(() => {
    if (!trader || !account) return;
    let live = true;
    setSymbols(null);
    readSymbols(account)
      .then((list) => {
        if (!live) return;
        setSymbols(list);
        // A new account the owner picked starts on its first symbol; the saved pair is kept
        // as it is even when this account no longer lists it.
        if (edited.current) setSymbol((old) => (list.includes(old) ? old : (list[0] ?? "")));
      })
      .catch((failure: unknown) => {
        if (live) {
          setSymbols([]);
          setError(failure);
        }
      });
    return () => {
      live = false;
    };
  }, [trader, account]);
  const marketChanged =
    trader &&
    marketEdited &&
    Boolean(account && symbol) &&
    (account !== (agent.trading_account_id ?? "") || symbol !== (agent.trading_symbol ?? ""));
  const changed =
    name.trim() !== agent.name ||
    role.trim() !== (agent.description || agent.title || "") ||
    modelValue !== savedModel ||
    marketChanged;
  useEffect(() => {
    if (changed) markDirty();
    else clearDirty();
    return () => clearDirty();
  }, [changed]);
  const nameErr = tried && !name.trim() ? t`Enter a name.` : "";
  const roleErr = tried && !role.trim() ? t`Enter the role.` : "";

  const submit = async () => {
    setTried(true);
    if (!name.trim() || !role.trim() || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      await api.patch(`/agents/${agent.id}`, {
        name: name.trim(),
        description: role.trim(),
        ...(marketChanged
          ? {
              scope_mode: "flexible",
              trading_account_id: account,
              trading_symbol: symbol,
              expected_scope_revision: agent.scope_revision ?? 0,
            }
          : {}),
      });
      if (modelValue !== savedModel && model.value) {
        const picked = model.value.available.find((item) => modelKey(item) === modelValue);
        await api.put(`/agents/${agent.id}/model`, {
          ...(picked
            ? { mode: "fixed", primary: { provider: picked.provider, model: picked.model } }
            : { mode: "automatic" }),
          expected_revision: model.value.record.revision,
        });
      }
      clearDirty();
      data.refresh();
      toast(t`Saved`, { type: "success" });
      nav.back();
    } catch (failure) {
      setError(failure);
      setBusy(false);
    }
  };

  const brokerName = accountLabel(accounts, account);
  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="hero">
        <span className="edit-wrap">
          <AgentAvatar agent={agent} />
          <button
            type="button"
            className="pencil"
            aria-label={t`Edit avatar`}
            onClick={() => openAvatar(agent)}
          >
            <Icon name="edit" />
          </button>
        </span>
      </div>
      <label className="field">
        <span>
          <Trans>Name</Trans>
        </span>
        <input
          name="name"
          required
          maxLength={80}
          value={name}
          aria-invalid={Boolean(nameErr)}
          onChange={(event) => setName(event.target.value)}
        />
        {nameErr && <small className="field-err">{nameErr}</small>}
      </label>
      <label className="field">
        <span>
          <Trans>Role</Trans>
        </span>
        <input
          name="role"
          required
          maxLength={2000}
          value={role}
          aria-invalid={Boolean(roleErr)}
          onChange={(event) => setRole(event.target.value)}
        />
        {roleErr && <small className="field-err">{roleErr}</small>}
      </label>
      <label className="field">
        <span>
          <Trans>Model</Trans>
        </span>
        <select
          name="model"
          value={modelValue}
          disabled={!model.value}
          onChange={(event) => setChoice(event.target.value)}
        >
          <option value="">{t({ message: "Automatic", context: "model" })}</option>
          {(model.value?.available ?? []).map((item) => (
            <option key={modelKey(item)} value={modelKey(item)}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {trader ? (
        accounts.length ? (
          <>
            {accounts.length > 1 || !account ? (
              <label className="field">
                <span>
                  <Trans>Trading account</Trans>
                </span>
                <select
                  name="account"
                  value={account}
                  onChange={(event) => {
                    setMarketEdited(true);
                    setAccount(event.target.value);
                  }}
                >
                  {!account && <option value="">{t`Choose an account`}</option>}
                  {accounts.map((row) => (
                    <option key={row.id} value={row.id}>
                      {accountLabel(accounts, row.id)}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <div className="group">
                <div className="row">
                  <span className="body">
                    <Trans>Account</Trans>
                  </span>
                  <span className="value">
                    <bdi>{brokerName}</bdi>
                  </span>
                </div>
              </div>
            )}
            {!account ? null : symbols === null ? (
              <p className="acct-fetch">
                <Icon name="refresh" />
                <span>
                  <Trans>
                    Fetching the symbols from <bdi>{brokerName}</bdi>…
                  </Trans>
                </span>
              </p>
            ) : (
              <>
                <label className="field">
                  <span>
                    <Trans>Pair</Trans>
                  </span>
                  <select
                    name="symbol"
                    required
                    value={symbol}
                    onChange={(event) => {
                      setMarketEdited(true);
                      setSymbol(event.target.value);
                    }}
                  >
                    {/* The saved pair stays selectable even when the account no longer lists it. */}
                    {(symbol && !symbols.includes(symbol) ? [symbol, ...symbols] : symbols).map(
                      (item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <p className="field-note">
                  <Icon name="refresh" />
                  <span>
                    <Trans>
                      From the symbols of the account <bdi>{brokerName}</bdi>, fetched
                      automatically.
                    </Trans>
                  </span>
                </p>
              </>
            )}
            {marketChanged && (
              <p className="note" role="status">
                <Trans>
                  Changing the market makes this agent's account and pair a flexible default. A
                  signed grant stays on its own account and pair: outside it, every order is shown
                  to you for approval before it is sent.
                </Trans>
              </p>
            )}
          </>
        ) : (
          connections.value && (
            <>
              <div className="group">
                <div className="row">
                  <span className="body">
                    <Trans>Account</Trans>
                  </span>
                  <span className="value">
                    <Trans>Not linked</Trans>
                  </span>
                </div>
              </div>
              <p className="note">
                <Trans>
                  Link a trading account from Settings → Integrations to choose the pair from its
                  symbols.
                </Trans>
              </p>
            </>
          )
        )
      ) : (
        agent.trading_symbol && (
          <div className="group">
            <div className="row">
              <span className="body">
                <Trans>Linked symbol</Trans>
              </span>
              <span className="value ltr">{agent.trading_symbol}</span>
            </div>
          </div>
        )
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="actions">
        <button type="submit" className="btn primary" disabled={busy}>
          <Trans>Save</Trans>
        </button>
      </div>
    </form>
  );
}
