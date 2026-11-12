import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon, PairIcon } from "@lonora/ui-web";
import { type FormEvent, type ReactNode, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { api } from "../../lib/api";
import { readAccount } from "../../lib/trading";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { clearDirty, markDirty, useNavigation } from "../navigation";
import { NotFoundPage } from "../StatePage";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import type { BrokerConnectionRow } from "./IntegrationsPage";
import { Empty, Note, useLoad, ValueRow } from "./ui";

type TestState = { ok: boolean; text: ReactNode } | null;
function TestResult({ state }: { state: TestState }) {
  if (!state) return null;
  return (
    <p className="note" role="status" id="connection-result">
      <Icon name={state.ok ? "check" : "alert"} /> {state.text}
    </p>
  );
}

/** One form value, from its element name. */
const field = (form: HTMLFormElement, name: string) =>
  ((form.elements.namedItem(name) as HTMLInputElement | null)?.value ?? "").trim();

/** The trading adapters this form links, with the fields each one takes (Q52): «تجريبي» (the
 * simulation provider). A local definition: the server has no provider catalog route. */
export type BrokerField = {
  name: string;
  kind: "text" | "password";
  required: boolean;
  secret: boolean;
};
export type BrokerProvider = {
  provider: string;
  environment: "broker" | "simulation";
  fields: BrokerField[];
};
export function brokerProviders(): Promise<BrokerProvider[]> {
  // A real (MetaApi) account is connected from chat: Lonora provisions it (mandate 9.2).
  return Promise.resolve([
    {
      provider: "simulation",
      environment: "simulation",
      fields: [{ name: "account_id", kind: "text", required: true, secret: false }],
    },
  ]);
}
const brokerName = (provider: string) =>
  provider === "simulation"
    ? t`Demo account`
    : provider === "metaapi"
      ? "MetaApi (MetaTrader)"
      : provider;
const fieldLabel = (field: BrokerField) =>
  field.name === "account_id" ? t`Account number` : field.name;

/* «ربط حساب تداول» (brokerFormPage 8701-8703): only «تجريبي», the simulation provider; a real
   account is connected from chat (mandate 9.2). «اختبار الاتصال» is a round trip that stores nothing. */
export function BrokerFormPage() {
  const nav = useNavigation();
  const toast = useToast();
  const catalog = useLoad(brokerProviders, []);
  const [provider, setProvider] = useState("simulation");
  const [test, setTest] = useState<TestState>(null);
  const [busy, setBusy] = useState(false);
  const entry = catalog.value?.find((item) => item.provider === provider);
  const body = (form: HTMLFormElement) => ({
    provider,
    enabled: true,
    ...Object.fromEntries(
      (entry?.fields ?? []).map((item) => [item.name, field(form, item.name) || null]),
    ),
  });
  const valid = (form: HTMLFormElement) => {
    if (!entry) return toast(t`Choose the broker`, { type: "warn" }), false;
    const missing = entry.fields.find((item) => item.required && !field(form, item.name));
    if (missing) return toast(t`Enter the account number`, { type: "warn" }), false;
    return true;
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!valid(form) || busy) return;
    setBusy(true);
    try {
      const row = await api.post<BrokerConnectionRow>("/trading/connections", body(form));
      clearDirty();
      toast(t`The account is linked`, { type: "success" });
      nav.go(`/app/broker-account/${row.id}`, { replace: true });
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <form noValidate onSubmit={submit} onInput={markDirty}>
      <label className="field">
        <span>
          <Trans>Broker</Trans>
        </span>
        <select
          name="broker"
          required
          value={provider}
          onChange={(event) => {
            setProvider(event.target.value);
            setTest(null);
          }}
        >
          {(catalog.value ?? []).map((item) => (
            <option key={item.provider} value={item.provider}>
              {brokerName(item.provider)}
            </option>
          ))}
        </select>
      </label>
      {entry?.environment === "simulation" && <ValueRow label={t`Account type`} value={t`Demo`} />}
      {entry?.fields.map((item) => (
        <label className="field" key={`${provider}:${item.name}`}>
          <span>{fieldLabel(item)}</span>
          <input
            name={item.name}
            type={item.kind === "password" ? "password" : "text"}
            required={item.required}
            dir="ltr"
            maxLength={item.secret ? 4096 : 120}
            autoComplete="off"
            placeholder={item.name === "account_id" ? t`e.g. 7310` : undefined}
          />
        </label>
      ))}
      <TestResult state={test} />
      <button
        type="button"
        className="btn full outline"
        disabled={busy}
        onClick={async (event) => {
          const form = event.currentTarget.form;
          if (!form || !valid(form)) return;
          setBusy(true);
          setTest(null);
          try {
            await api.post("/trading/connections/test", body(form));
            setTest({ ok: true, text: <Trans>The connection works</Trans> });
          } catch (error) {
            setTest({ ok: false, text: userError(error) });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Trans>Test the connection</Trans>
      </button>
      <Note>
        <Trans>
          After linking, the account's trading symbols are fetched from the broker and appear in the
          pair pickers.
        </Trans>
      </Note>
      <Note>
        <Trans>A real trading account is connected from chat: ask Lonora to connect it.</Trans>
      </Note>
      <div className="actions">
        <button type="submit" className="btn primary" disabled={busy}>
          <Trans>Link the account</Trans>
        </button>
      </div>
    </form>
  );
}

/* One account (accountPage 8705-8717, symGrid 8727-8733): hero, balance, type, the symbols in two
   columns, the agents on it and «فصل الحساب» with what the server really does. */
export function BrokerAccountPage({ connectionId }: { connectionId: string }) {
  const data = useShellData();
  const nav = useNavigation();
  const sheets = useSheets();
  const toast = useToast();
  const connections = useLoad(() => api.get<BrokerConnectionRow[]>("/trading/connections"), []);
  const row = connections.value?.find((item) => item.id === connectionId);
  const account = useLoad(() => readAccount(connectionId), [connectionId]);
  const snap = account.value?.account;
  const symbols = useLoad(
    () => api.get<string[]>(`/market/symbols?account_id=${encodeURIComponent(connectionId)}`),
    [connectionId],
  );
  if (connections.value && !row)
    return (
      <>
        <Empty>
          <Trans>No trading account is linked.</Trans>
        </Empty>
        <button type="button" className="btn full primary" onClick={() => nav.go("/app/broker")}>
          <Trans>Link a trading account</Trans>
        </button>
      </>
    );
  if (!row) return connections.error ? <NotFoundPage /> : null;
  const demo = row.payload.provider === "simulation";
  const agents = data.agents.filter((agent) => agent.trading_account_id === row.id);
  const names = agents.map((agent) => agent.name).join("، ");
  const number = snap?.login || row.payload.account_id;
  const broker = snap?.broker ?? (demo ? t`Demo account` : "MetaApi");
  const list = symbols.value ?? [];
  const remove = () => {
    const title = t`Unlink the account`;
    sheets.open({
      id: "acct-remove",
      title,
      label: title,
      body: (
        <>
          <p>
            <Trans>
              The account <span className="ltr">{number}</span> at <bdi>{broker}</bdi> is unlinked.
            </Trans>{" "}
            {agents.length > 0 && (
              <Trans>
                Any signed delegation on this account is revoked, and {names} go back to «Execute
                with approval» without an account until you choose another one.
              </Trans>
            )}
          </p>
          <div className="actions">
            <button type="button" className="btn outline" onClick={() => sheets.close()}>
              <Trans>Cancel</Trans>
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={async () => {
                try {
                  await api.delete(`/trading/connections/${encodeURIComponent(row.id)}`);
                  sheets.close(true);
                  data.refresh();
                  nav.go("/app/integrations", { replace: true });
                  toast(t`Account ${number} is unlinked`, { type: "success" });
                } catch (error) {
                  sheets.close();
                  toast(userError(error), { type: "error" });
                }
              }}
            >
              <Trans>Unlink the account</Trans>
            </button>
          </div>
        </>
      ),
    });
  };
  const needsSnapshot =
    demo &&
    (account.error as { code?: string } | undefined)?.code === "simulation_snapshot_required";
  if (needsSnapshot)
    return (
      <>
        <SimulationImport
          connectionId={row.id}
          number={number}
          onImported={() => {
            account.reload();
            symbols.reload();
          }}
        />
        <button type="button" className="btn full danger" onClick={remove}>
          <Trans>Unlink the account</Trans>
        </button>
      </>
    );
  const cells = list.map((symbol) => {
    const who = agents
      .filter((agent) => agent.trading_symbol === symbol)
      .map((agent) => agent.name);
    return (
      // biome-ignore lint/a11y/useSemanticElements: the reference's own role on its row
      <div className="sym-cell" role="listitem" key={symbol}>
        <PairIcon symbol={symbol} />
        <span className="sym-t">
          <strong>
            <span className="ltr">{symbol}</span>
          </strong>
          {who.length > 0 && (
            <small>
              <span className="sym-who">{who.join("، ")}</span>
            </small>
          )}
        </span>
      </div>
    );
  });
  if (list.length % 2)
    cells.push(<div className="sym-cell sym-empty" aria-hidden="true" key="pad" />);
  return (
    <>
      <div className="acct-hero">
        <span className="row-icon">
          <Icon name="trend" />
        </span>
        <div>
          <strong>
            <bdi>{broker}</bdi>
          </strong>
          <small>
            <span className="ltr">{number}</span>
            {demo ? ` · ${t`Demo`}` : ""}
            {snap?.server ? (
              <>
                {" "}
                · <span className="ltr">{snap.server}</span>
              </>
            ) : null}
          </small>
        </div>
      </div>
      <div className="group">
        <ValueRow
          label={t`Balance`}
          value={
            snap ? (
              <span className="ltr">
                {snap.balance} {snap.currency}
              </span>
            ) : account.error ? (
              userError(account.error)
            ) : (
              "…"
            )
          }
        />
        {demo && <ValueRow label={t`Account type`} value={t`Demo`} />}
      </div>
      <h3>
        {symbols.loading ? (
          <Trans>Available symbols</Trans>
        ) : (
          <Trans>Available symbols · {list.length}</Trans>
        )}
      </h3>
      {symbols.loading ? (
        <p className="acct-fetch">
          <Icon name="refresh" />
          <span>
            <Trans>
              Fetching the symbols from <bdi>{broker}</bdi>…
            </Trans>
          </span>
        </p>
      ) : symbols.error ? (
        <p className="note" role="alert">
          {userError(symbols.error)}
        </p>
      ) : (
        // biome-ignore lint/a11y/useSemanticElements: the reference's own role on its row
        <div
          className={`sym-grid${list.length > 6 ? " is-scroll" : ""}`}
          role="list"
          aria-label={t`Available symbols`}
          tabIndex={list.length > 6 ? 0 : undefined}
        >
          {cells}
        </div>
      )}
      <p className="muted acct-note">
        <Trans>
          Fetched from the broker account, and shown in the pair pickers when creating an agent and
          in delegation.
        </Trans>
      </p>
      {!symbols.loading && (
        <button
          type="button"
          className="btn full outline"
          onClick={() => {
            symbols.reload();
          }}
        >
          <Trans>Refresh the symbols</Trans>
        </button>
      )}
      <h3>
        <Trans>Agents on this account</Trans>
      </h3>
      {agents.length ? (
        <div className="group">
          {agents.map((agent) => (
            <button
              type="button"
              className="row"
              key={agent.id}
              onClick={() => nav.go(`/app/${agent.id}`)}
            >
              <AgentAvatar agent={agent} />
              <span className="body">
                <strong>
                  <bdi>{agent.name}</bdi>
                </strong>
                {agent.trading_symbol && (
                  <small>
                    <span className="ltr">{agent.trading_symbol}</span>
                  </small>
                )}
              </span>
              <span className="chevron">
                <Icon name="chev" />
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">
          <Trans>No agent works on this account.</Trans>
        </p>
      )}
      <button type="button" className="btn full danger" onClick={remove}>
        <Trans>Unlink the account</Trans>
      </button>
    </>
  );
}

/* «حساب تجريبي» trades against a market snapshot the owner imports (balance, currency,
   instruments, quotes and candles; the server's simulation format). Nothing is invented here:
   until a snapshot is imported the account has no symbols. */
function SimulationImport({
  connectionId,
  number,
  onImported,
}: {
  connectionId: string;
  number: string;
  onImported: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <>
      <div className="acct-hero">
        <span className="row-icon">
          <Icon name="trend" />
        </span>
        <div>
          <strong>
            <bdi>{t`Demo account`}</bdi>
          </strong>
          <small>
            <span className="ltr">{number}</span> · {t`Demo`}
          </small>
        </div>
      </div>
      <p className="muted">
        <Trans>
          A demo account trades against market data you import: the balance, the symbols, their
          prices and candles. Import a snapshot file to use it.
        </Trans>
      </p>
      <label className="btn full primary">
        <Trans>Import the demo account data</Trans>
        <input
          type="file"
          accept="application/json,.json"
          hidden
          disabled={busy}
          onChange={async (event) => {
            const file = event.currentTarget.files?.[0];
            event.currentTarget.value = "";
            if (!file) return;
            setBusy(true);
            try {
              const snapshot = JSON.parse(await file.text()) as unknown;
              await api.post(
                `/trading/connections/${encodeURIComponent(connectionId)}/simulation`,
                {
                  snapshot,
                },
              );
              toast(t`The demo account data is imported`, { type: "success" });
              onImported();
            } catch (error) {
              toast(
                error instanceof SyntaxError ? t`The file is not valid JSON.` : userError(error),
                {
                  type: "error",
                },
              );
            } finally {
              setBusy(false);
            }
          }}
        />
      </label>
    </>
  );
}

const PROVIDER_NAMES: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  zai: "Z.ai",
  openrouter: "OpenRouter",
};
export const providerName = (id: string) => PROVIDER_NAMES[id] ?? id;

/* «مزوّدو النماذج» (route `providers`): the server's providers that have a key. */
export function ProvidersPage() {
  const nav = useNavigation();
  const providers = useLoad(() => api.get<{ id: string; configured: boolean }[]>("/providers"), []);
  const configured = (providers.value ?? []).filter((item) => item.configured);
  return (
    <>
      {configured.length ? (
        <div className="group">
          {configured.map((item) => (
            <button
              type="button"
              className="row"
              key={item.id}
              onClick={() => nav.go(`/app/provider/${item.id}`)}
            >
              <Icon name="cpu" />
              <span className="body">
                <strong>{providerName(item.id)}</strong>
                <small>
                  <Trans>Key saved · never shown again</Trans>
                </small>
              </span>
              <span className="chevron">
                <Icon name="chev" />
              </span>
            </button>
          ))}
        </div>
      ) : providers.loading ? null : (
        <Empty>
          <Trans>You have not added a provider yet.</Trans>
        </Empty>
      )}
      <button type="button" className="btn full primary" onClick={() => nav.go("/app/provider")}>
        <Trans>Add a provider</Trans>
      </button>
    </>
  );
}

/* The provider form (route `provider`): the provider, the API key (show/hide), «اختبار الاتصال»
   (POST /providers/{id}/test: lists the models without storing the key) and save (the key is
   stored encrypted, then the catalog is discovered). */
export function ProviderFormPage({ initial }: { initial?: string }) {
  if (initial !== undefined && !Object.hasOwn(PROVIDER_NAMES, initial)) return <NotFoundPage />;
  return <ProviderForm initial={initial} />;
}
function ProviderForm({ initial }: { initial?: string }) {
  const nav = useNavigation();
  const toast = useToast();
  const providers = useLoad(() => api.get<{ id: string; configured: boolean }[]>("/providers"), []);
  const [provider, setProvider] = useState(initial ?? "");
  const [shown, setShown] = useState(false);
  const [test, setTest] = useState<TestState>(null);
  const [busy, setBusy] = useState(false);
  const key = (form: HTMLFormElement | null) => (form ? field(form, "key") : "");
  const check = (form: HTMLFormElement | null) => {
    if (!provider) return toast(t`Choose the provider`, { type: "warn" }), false;
    if (key(form).length < 8) return toast(t`Enter the API key`, { type: "warn" }), false;
    return true;
  };
  return (
    <form
      noValidate
      onInput={markDirty}
      onSubmit={async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        if (!check(form) || busy) return;
        setBusy(true);
        try {
          await api.put(`/providers/${encodeURIComponent(provider)}/credential`, {
            api_key: key(form),
          });
          await api
            .post(`/providers/${encodeURIComponent(provider)}/discover`, {})
            .catch(() => undefined);
          clearDirty();
          toast(t`Saved`, { type: "success" });
          nav.go("/app/providers", { replace: true });
        } catch (error) {
          toast(userError(error), { type: "error" });
        } finally {
          setBusy(false);
        }
      }}
    >
      <label className="field">
        <span>
          <Trans>Provider</Trans>
        </span>
        <select
          name="provider"
          required
          value={provider}
          onChange={(event) => {
            setProvider(event.target.value);
            setTest(null);
          }}
        >
          <option value="">{t`Choose the provider`}</option>
          {(providers.value ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {providerName(item.id)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>
          <Trans>API key</Trans>
        </span>
        <div className="secret">
          <input
            name="key"
            type={shown ? "text" : "password"}
            required
            autoComplete="off"
            dir="ltr"
          />
          <button
            type="button"
            className="icon"
            aria-label={shown ? t`Hide the key` : t`Show the key`}
            aria-pressed={shown}
            onClick={() => setShown(!shown)}
          >
            <Icon name="eye" />
          </button>
        </div>
        <small>
          <Trans>The key is stored encrypted and is never shown again.</Trans>
        </small>
      </label>
      <TestResult state={test} />
      <button
        type="button"
        className="btn full outline"
        disabled={busy}
        onClick={async (event) => {
          const form = event.currentTarget.form;
          if (!check(form)) return;
          setBusy(true);
          setTest(null);
          try {
            const result = await api.post<{ models: string[] }>(
              `/providers/${encodeURIComponent(provider)}/test`,
              {
                api_key: key(form),
              },
            );
            const count = result.models.length;
            setTest({ ok: true, text: t`The connection works · ${count} models available` });
          } catch (error) {
            setTest({ ok: false, text: userError(error) });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Trans>Test the connection</Trans>
      </button>
      <div className="actions">
        <button type="submit" className="btn primary" disabled={busy}>
          <Trans>Save the settings</Trans>
        </button>
      </div>
    </form>
  );
}

/* «إضافة خادم MCP» (route `mcp`) under Q55/Q56: a remote server only (Streamable HTTP), no per-agent
   allow list. A new server lands in the integrations list as «غير معتمد» until approved. */
export function McpFormPage() {
  const nav = useNavigation();
  const toast = useToast();
  const [auth, setAuth] = useState<"none" | "token">("none");
  const [test, setTest] = useState<TestState>(null);
  const [busy, setBusy] = useState(false);
  const values = (form: HTMLFormElement) => ({
    name: field(form, "name"),
    url: field(form, "url"),
    token: auth === "token" ? field(form, "token") : "",
  });
  const check = (form: HTMLFormElement | null) => {
    if (!form) return false;
    const { name, url, token } = values(form);
    if (!name) return toast(t`Enter the server name`, { type: "warn" }), false;
    if (!/^https:\/\/\S+/.test(url))
      return toast(t`Enter a link that starts with https://`, { type: "warn" }), false;
    if (auth === "token" && !token)
      return toast(t`Enter the access token`, { type: "warn" }), false;
    return true;
  };
  return (
    <form
      noValidate
      onInput={markDirty}
      onSubmit={async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        if (!check(form) || busy) return;
        setBusy(true);
        const { name, url, token } = values(form);
        try {
          const secret = token
            ? await api.post<{ id: string }>("/integrations/secrets", {
                name: `mcp-${name}`.slice(0, 80),
                value: token,
              })
            : null;
          await api.post("/mcp", {
            payload: { name, transport: "http", url, secret_id: secret?.id ?? null, enabled: true },
          });
          clearDirty();
          toast(t`The server is added`, { type: "success" });
          nav.go("/app/integrations", { replace: true });
        } catch (error) {
          toast(userError(error), { type: "error" });
        } finally {
          setBusy(false);
        }
      }}
    >
      <label className="field">
        <span>
          <Trans>Server name</Trans>
        </span>
        <input name="name" required maxLength={80} placeholder={t`Research tools`} />
      </label>
      <ValueRow label={t`Connection type`} value="Streamable HTTP" />
      <label className="field">
        <span>
          <Trans>Server address</Trans>
        </span>
        <input
          name="url"
          type="url"
          required
          dir="ltr"
          placeholder="https://mcp.example.com/mcp"
          autoComplete="off"
        />
      </label>
      <label className="field">
        <span>
          <Trans>Authentication</Trans>
        </span>
        <select
          name="auth"
          value={auth}
          onChange={(event) => setAuth(event.target.value === "token" ? "token" : "none")}
        >
          <option value="none">{t`No authentication`}</option>
          <option value="token">{t`Access token`}</option>
        </select>
      </label>
      {auth === "token" && (
        <label className="field">
          <span>
            <Trans>Access token — stored encrypted, never shown again</Trans>
          </span>
          <input name="token" type="password" dir="ltr" autoComplete="off" />
        </label>
      )}
      <TestResult state={test} />
      <button
        type="button"
        className="btn full outline"
        disabled={busy}
        onClick={async (event) => {
          const form = event.currentTarget.form;
          if (!check(form) || !form) return;
          setBusy(true);
          setTest(null);
          const { url, token } = values(form);
          try {
            const result = await api.post<{ tools: string[]; blocked: string[] }>("/mcp/test", {
              url,
              token: token || null,
            });
            const count = result.tools.length;
            setTest({ ok: true, text: t`The connection works · ${count} tools` });
          } catch (error) {
            setTest({ ok: false, text: userError(error) });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Trans>Test the connection</Trans>
      </button>
      <Note>
        <Trans>
          Remote servers only. You review and approve its tools before any agent uses them.
        </Trans>
      </Note>
      <div className="actions">
        <button type="submit" className="btn primary" disabled={busy}>
          <Trans>Add the server</Trans>
        </button>
      </div>
    </form>
  );
}
