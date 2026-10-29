import { useLingui } from "@lingui/react";
import type {
  AccountAuthority,
  Agent,
  AgentPermissionLevel,
  DeviceChallenge,
  PermissionCustomization,
  PermissionState,
  Resource,
} from "@lonora/contracts";
import {
  accountAuthorityLabels,
  activateAccountAuthority,
  agentPermissionLevels,
  authorityStatus,
  customizedManagementProposal,
  emptyManagementCustomization,
  webDeviceProof,
  webDeviceSupported,
} from "@lonora/core";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@lonora/ui-web";
import { Check, ChevronDown, Eye, ShieldCheck, X, Zap } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useOverlayHistory } from "../../hooks/useOverlayHistory";
import { ApiError, api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { PermissionEditor, PermissionSummary, permissionAccountName } from "./PermissionEditor";
import { permissionLabels } from "./permission-labels";
import "./agent-permissions.css";

const unsavedPreferences = new Map<string, PermissionCustomization>();
type AgentBinding = Pick<Agent, "trading_account_id" | "trading_symbol">;
function defaults(agent: AgentBinding): PermissionCustomization {
  return {
    ...emptyManagementCustomization(),
    account_id: agent.trading_account_id ?? "",
    symbol_scope: agent.trading_symbol ? "selected" : "account",
    symbols: agent.trading_symbol ? [agent.trading_symbol] : [],
  };
}
function bindDraft(agent: AgentBinding, draft: PermissionCustomization): PermissionCustomization {
  return agent.trading_account_id && agent.trading_symbol
    ? {
        ...draft,
        account_id: agent.trading_account_id,
        symbol_scope: "selected",
        symbols: [agent.trading_symbol],
      }
    : draft;
}
function useCompactSurface() {
  const [compact, setCompact] = useState(
    () => window.matchMedia("(max-width: 767px), (max-height: 500px)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia("(max-width: 767px), (max-height: 500px)");
    const change = () => setCompact(query.matches);
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  return compact;
}

/** One owner control for the actual composer and settings. Only server-verified
 * grants establish autonomy; presentation and saved preferences never do. */
export function AgentPermissions({
  agent,
  threadId,
  surface = "settings",
}: {
  agent: Agent;
  threadId: string;
  surface?: "composer" | "settings";
}) {
  const { i18n } = useLingui();
  const locale = i18n.locale;
  const rtl = locale.startsWith("ar");
  const text = permissionLabels[rtl ? "ar" : "en"];
  const labels = accountAuthorityLabels[rtl ? "ar" : "en"];
  const { owner, events, connected } = useClient();
  const relevantCursor = useRef(0);
  for (const event of events) {
    if (
      (event.agent_id === agent.id || event.payload.agent_id === agent.id) &&
      ["agent.permission.updated", "account_authority.updated", "agent.updated"].includes(
        event.kind,
      )
    )
      relevantCursor.current = Math.max(relevantCursor.current, event.cursor);
  }
  const permissionRevision = relevantCursor.current;
  const scope = `${owner.id}:${agent.id}`;
  const boundAccount = agent.trading_account_id;
  const boundSymbol = agent.trading_symbol;
  const mounted = useRef(true);
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const [state, setState] = useState<PermissionState | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const [draft, setDraft] = useState<PermissionCustomization>(() =>
    bindDraft(agent, unsavedPreferences.get(scope) ?? defaults(agent)),
  );
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const dirty = useRef(unsavedPreferences.has(scope));
  const [picker, setPicker] = useState(false);
  const [flow, setFlow] = useState<"editor" | "review" | "account" | null>(null);
  const [review, setReview] = useState<AccountAuthority | null>(null);
  const [selected, setSelected] = useState<AgentPermissionLevel>("analysis");
  const [accounts, setAccounts] = useState<Resource[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbolError, setSymbolError] = useState<string>();
  const [currency, setCurrency] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const interaction = useRef(0);
  const [error, setError] = useState<unknown>();
  const [saved, setSaved] = useState(false);
  const [phase, setPhase] = useState<
    "preparing" | "awaiting" | "verifying" | "activated" | "cancelled" | "failed" | null
  >(null);
  const [enroll, setEnroll] = useState(false);
  const [password, setPassword] = useState("");
  const [reload, setReload] = useState(0);
  const compact = useCompactSurface();
  const radioName = useId();
  const flowActive = flow !== null;
  const path = `/agents/${encodeURIComponent(agent.id)}/permissions`;
  const supported = webDeviceSupported();
  const alive = useCallback(() => mounted.current && currentScope.current === scope, [scope]);
  const accept = useCallback(
    (next: PermissionState) => {
      if (!alive()) return;
      // Parallel read responses may arrive after a mutation. Revisions are monotonic.
      if (stateRef.current && next.revision < stateRef.current.revision) return;
      stateRef.current = next;
      setState(next);
      setSelected(next.requested_level);
      if (!dirty.current) {
        const binding = { trading_account_id: boundAccount, trading_symbol: boundSymbol };
        setDraft(bindDraft(binding, next.customization ?? defaults(binding)));
      }
      setReview((current) =>
        current
          ? next.pending_authority?.id === current.id
            ? next.pending_authority
            : (next.active_authorities.find((row) => row.id === current.id) ?? null)
          : null,
      );
    },
    [alive, boundAccount, boundSymbol],
  );
  const fresh = useCallback(async () => {
    const next = await api.get<PermissionState>(path);
    accept(next);
    return next;
  }, [path, accept]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    void permissionRevision;
    void connected;
    void reload;
    void api
      .get<PermissionState>(path)
      .then((next) => {
        if (active) {
          accept(next);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (active && !isRequestCancelled(cause)) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [path, permissionRevision, connected, reload, accept]);
  useEffect(() => {
    const reconcile = () => {
      if (document.visibilityState === "visible") setReload((value) => value + 1);
    };
    document.addEventListener("visibilitychange", reconcile);
    window.addEventListener("online", reconcile);
    // An unavailable event connection has a bounded visible-tab fallback.
    const timer = !connected ? setInterval(reconcile, 60000) : undefined;
    return () => {
      document.removeEventListener("visibilitychange", reconcile);
      window.removeEventListener("online", reconcile);
      if (timer) clearInterval(timer);
    };
  }, [connected]);
  useEffect(() => {
    if (!state) return;
    const deadlines = [
      ...state.active_authorities.map((row) => row.valid_until),
      state.pending_authority?.activation_expires_at,
    ]
      .filter((value): value is string => Boolean(value))
      .map(Date.parse)
      .filter((value) => value > Date.now());
    if (!deadlines.length) return;
    const timer = setTimeout(
      () => setReload((value) => value + 1),
      Math.min(2147483647, Math.max(50, Math.min(...deadlines) - Date.now() + 50)),
    );
    return () => clearTimeout(timer);
  }, [state]);
  useEffect(() => {
    if (!flowActive) return;
    let active = true;
    void api
      .get<Resource[]>("/trading/connections")
      .then((value) => {
        if (active) setAccounts(value);
      })
      .catch((cause) => {
        if (active && !isRequestCancelled(cause)) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [flowActive]);
  const accountContext = flow === "review" && review ? review.account_id : draft.account_id;
  useEffect(() => {
    setSymbols([]);
    setCurrency("");
    setSymbolError(undefined);
    if (!flowActive || !accountContext) return;
    let active = true;
    void api
      .get<{ account: { currency: string } }>(
        `/trading/accounts/${encodeURIComponent(accountContext)}`,
      )
      .then((value) => {
        if (active) setCurrency(value.account.currency);
      })
      .catch((cause) => {
        if (active && !isRequestCancelled(cause)) setSymbolError(userError(cause));
      });
    if (!agent.trading_symbol)
      void api
        .get<string[]>(`/market/symbols?account_id=${encodeURIComponent(accountContext)}`)
        .then((value) => {
          if (active) setSymbols(value);
        })
        .catch((cause) => {
          if (active && !isRequestCancelled(cause)) setSymbolError(userError(cause));
        });
    return () => {
      active = false;
    };
  }, [flowActive, accountContext, agent.trading_symbol]);
  const edit = (value: PermissionCustomization) => {
    const next = bindDraft(agent, value);
    dirty.current = true;
    draftRef.current = next;
    unsavedPreferences.set(scope, next);
    setDraft(next);
    setSaved(false);
  };
  const persist = useCallback(
    async (value: PermissionCustomization) => {
      const latest = await fresh();
      const next = await api.put<PermissionState>(`${path}/customization`, {
        expected_revision: latest.revision,
        customization: value,
      });
      if (alive()) {
        if (draftRef.current === value) {
          dirty.current = false;
          unsavedPreferences.delete(scope);
        }
        accept(next);
        setSaved(true);
      }
      return next;
    },
    [fresh, path, alive, accept, scope],
  );
  const execute = useCallback(
    async (operation: () => Promise<void>) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      setError(undefined);
      try {
        await operation();
      } catch (cause) {
        if (alive() && !isRequestCancelled(cause)) {
          setError(cause);
          if (cause instanceof ApiError && cause.code === "device_registration_required") {
            setEnroll(true);
            setPhase(null);
          } else
            setPhase(
              cause instanceof Error &&
                "code" in cause &&
                cause.code === "device_authorization_cancelled"
                ? "cancelled"
                : "failed",
            );
          if (cause instanceof ApiError && cause.code === "version_conflict")
            void fresh().catch(() => undefined);
        }
      } finally {
        busyRef.current = false;
        if (alive()) setBusy(false);
      }
    },
    [alive, fresh],
  );
  useEffect(() => {
    if (flow !== "editor" || !dirty.current || busy) return;
    const timer = setTimeout(() => {
      void execute(async () => {
        await persist(draft);
      });
    }, 700);
    return () => clearTimeout(timer);
  }, [draft, flow, busy, execute, persist]);
  const close = () => {
    interaction.current += 1;
    setPicker(false);
    setFlow(null);
    setPassword("");
    setEnroll(false);
    setPhase(null);
    if (dirty.current && !busyRef.current)
      void execute(async () => {
        await persist(draftRef.current);
      });
  };
  useOverlayHistory(Boolean(flow) || (compact && picker), close);
  const proposal = customizedManagementProposal(draft, {
    thread_id: threadId,
    account_id: draft.account_id,
    symbol_scope: draft.symbol_scope,
    symbols: draft.symbols,
  });
  const prepare = async (value: PermissionCustomization, persistPreferences: boolean) => {
    const started = interaction.current;
    const body = customizedManagementProposal(value, {
      thread_id: threadId,
      account_id: value.account_id,
      symbol_scope: value.symbol_scope,
      symbols: value.symbols,
    });
    if (!body) {
      setError(new Error(text.invalid));
      return;
    }
    setPhase("preparing");
    const latest = persistPreferences ? await persist(value) : await fresh();
    const row = await api.post<AccountAuthority>(
      `/agents/${encodeURIComponent(agent.id)}/account-authorities?permission_revision=${latest.revision}`,
      body,
    );
    if (!alive()) return;
    if (interaction.current !== started) {
      await fresh();
      return;
    }
    setReview(row);
    setFlow("review");
    setPhase(null);
    setPassword("");
    setEnroll(false);
    await fresh();
  };
  const choose = (level: AgentPermissionLevel) => {
    setPicker(false);
    setError(undefined);
    setPhase(null);
    if (level !== "autonomous") {
      void execute(async () => {
        const latest = await fresh();
        const next = await api.put<PermissionState>(path, {
          level,
          expected_revision: latest.revision,
        });
        accept(next);
        setReview(null);
        setFlow(null);
        setPassword("");
        setEnroll(false);
      });
      return;
    }
    setSelected("autonomous");
    void execute(async () => {
      const latest = await fresh();
      const existing =
        latest.pending_authority && authorityStatus(latest.pending_authority) === "pending"
          ? latest.pending_authority
          : latest.active_authorities[0];
      if (existing) {
        setReview(existing);
        setFlow("review");
        setSelected("autonomous");
        return;
      }
      const value = bindDraft(
        agent,
        dirty.current ? draftRef.current : (latest.customization ?? defaults(agent)),
      );
      setDraft(value);
      draftRef.current = value;
      setSelected("autonomous");
      if (!value.account_id) {
        setFlow("account");
        return;
      }
      await prepare(value, dirty.current);
    });
  };
  const statusText =
    state?.status === "awaiting_authorization"
      ? text.pending
      : state?.status === "authorization_expired"
        ? text.expired
        : state?.status === "autonomous_stopped"
          ? text.stopped
          : null;
  const reviewPending = Boolean(
    review && authorityStatus(review) === "pending" && state?.pending_authority?.id === review.id,
  );
  const reviewActive = Boolean(
    review &&
      authorityStatus(review) === "active" &&
      state?.active_authorities.some((row) => row.id === review.id),
  );
  const reviewableAuthorities = [
    ...(state?.pending_authority && authorityStatus(state.pending_authority) === "pending"
      ? [state.pending_authority]
      : []),
    ...(state?.active_authorities.filter((row) => authorityStatus(row) === "active") ?? []),
  ];
  const showAdvanced = selected === "autonomous";
  const openAdvanced = () => {
    setPicker(false);
    setFlow("editor");
    setError(undefined);
    setPhase(null);
    setPassword("");
    setEnroll(false);
  };
  const inlineError = !flow && error != null && (
    <span className="permission-inline-error" role="alert">
      {state ? userError(error) : text.permissionUnavailable}
      <button type="button" onClick={() => setReload((value) => value + 1)}>
        {text.retry}
      </button>
    </span>
  );
  const optionList = (
    <div className="permission-options" data-testid="permission-options" dir={rtl ? "rtl" : "ltr"}>
      <h3>{text.title}</h3>
      <div role="radiogroup" aria-label={text.title}>
        {agentPermissionLevels.map((level) => (
          <label key={level} className="permission-level-option" data-selected={selected === level}>
            <input
              type="radio"
              name={radioName}
              checked={selected === level}
              data-testid={`permission-option-${level}`}
              disabled={busy || !state || (agent.role === "delegated" && level !== "analysis")}
              onChange={() => choose(level)}
              onClick={() => {
                if (selected === level) choose(level);
              }}
            />
            <span>
              <strong>{text[level]}</strong>
              <small>{text[`${level}Hint`]}</small>
            </span>
            {selected === level && <Check size={17} />}
          </label>
        ))}
      </div>
      {showAdvanced && (
        <button
          type="button"
          data-testid="permission-advanced"
          className="permission-link"
          onClick={openAdvanced}
        >
          {text.advanced}
        </button>
      )}
      {surface === "composer" && inlineError}
      {statusText && <p className="permission-explanation">{statusText}</p>}
      <p className="permission-explanation">{text.stoppedHint}</p>
    </div>
  );
  const PermissionIcon =
    state?.effective_level === "autonomous"
      ? Zap
      : state?.effective_level === "supervised"
        ? ShieldCheck
        : Eye;
  const triggerLabel = state ? `${text.title}: ${text[state.effective_level]}` : text.loading;
  const trigger = (
    <>
      <PermissionIcon
        size={surface === "composer" ? 18 : 14}
        aria-hidden="true"
        data-permission-icon={state?.effective_level ?? "loading"}
      />
      <span className="permission-trigger-label">
        {state ? text[state.effective_level] : text.title}
      </span>
      <ChevronDown className="permission-trigger-chevron" size={12} aria-hidden="true" />
    </>
  );
  return (
    <div
      className={`agent-permissions${surface === "composer" ? " agent-permissions-composer" : ""}`}
      dir={rtl ? "rtl" : "ltr"}
      data-surface={surface}
    >
      {compact ? (
        <>
          <button
            type="button"
            className="permission-trigger"
            data-testid="permission-selector"
            aria-label={triggerLabel}
            title={triggerLabel}
            aria-haspopup="dialog"
            aria-expanded={picker}
            onClick={() => setPicker((value) => !value)}
          >
            {trigger}
          </button>
          <Dialog
            open={picker && !flow}
            onOpenChange={(open) => {
              if (!open) setPicker(false);
            }}
          >
            <DialogContent className="permission-picker-sheet" showCloseButton={false}>
              <DialogTitle className="sr-only">{text.title}</DialogTitle>
              <DialogDescription className="sr-only">{text.current}</DialogDescription>
              {optionList}
              <button
                type="button"
                className="permission-secondary"
                onClick={() => setPicker(false)}
              >
                {text.close}
              </button>
            </DialogContent>
          </Dialog>
        </>
      ) : (
        <Popover open={picker && !flow} onOpenChange={setPicker}>
          <PopoverTrigger
            type="button"
            className="permission-trigger"
            data-testid="permission-selector"
            aria-label={triggerLabel}
            title={triggerLabel}
          >
            {trigger}
          </PopoverTrigger>
          <PopoverContent className="permission-picker-popover" side="top" align="start">
            {optionList}
          </PopoverContent>
        </Popover>
      )}
      <span
        className={`permission-effective${surface === "composer" ? " sr-only" : ""}`}
        data-testid="permission-effective"
        data-level={state?.effective_level ?? "loading"}
        aria-live="polite"
      >
        {state ? statusText || text[state.effective_level] : text.loading}
      </span>
      {surface !== "composer" && inlineError}
      <Dialog
        open={Boolean(flow)}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <DialogContent
          className={`permission-dialog ${flow === "editor" ? "permission-dialog-editor" : "permission-dialog-review"}`}
          data-testid={flow === "editor" ? "permission-editor" : "permission-review"}
          dir={rtl ? "rtl" : "ltr"}
          showCloseButton={false}
        >
          <header className="permission-dialog-header">
            <DialogTitle>{flow === "editor" ? text.advanced : text.review}</DialogTitle>
            <button type="button" aria-label={text.close} onClick={close}>
              <X size={20} />
            </button>
            <DialogDescription>
              <bdi data-testid="permission-header-agent">{agent.name}</bdi>
              {" · "}
              {text.autonomousHint}
              {state && (
                <span className="permission-current-state">
                  {text.current}: {text[state.effective_level]}
                  {statusText ? ` · ${statusText}` : ""}
                </span>
              )}
            </DialogDescription>
          </header>
          <div className="permission-dialog-scroll">
            {flow === "review" && state && state.active_authorities.length > 0 && (
              <nav
                className="permission-authority-list"
                aria-label={text.authorizations}
                data-testid="permission-authorities"
              >
                <h3>{text.authorizations}</h3>
                {reviewableAuthorities.map((row) => (
                  <button
                    type="button"
                    key={row.id}
                    data-testid={`permission-authority-${row.id}`}
                    aria-pressed={review?.id === row.id}
                    disabled={busy}
                    onClick={() => {
                      setReview(row);
                      setPhase(null);
                      setEnroll(false);
                      setPassword("");
                      setError(undefined);
                    }}
                  >
                    <span>
                      <strong>
                        <bdi>{permissionAccountName(accounts, row.account_id, labels.account)}</bdi>
                      </strong>
                      <small>
                        <bdi>
                          {row.envelope.symbol_scope === "account"
                            ? text.accountWide
                            : row.envelope.symbols.join(" · ")}
                        </bdi>
                        {" · "}
                        {authorityStatus(row) === "active"
                          ? text.activeAuthorization
                          : text.pending}
                      </small>
                    </span>
                    {review?.id === row.id && <Check size={16} />}
                  </button>
                ))}
              </nav>
            )}
            {flow === "editor" ? (
              <div className="permission-editor-columns">
                <PermissionEditor
                  key={`editor:${agent.id}`}
                  agent={agent}
                  draft={draft}
                  onChange={edit}
                  accounts={accounts}
                  symbols={symbols}
                  currency={currency}
                  text={text}
                  labels={labels}
                  symbolError={symbolError}
                />
                <PermissionSummary
                  agentName={agent.name}
                  value={draft}
                  accounts={accounts}
                  currency={currency}
                  text={text}
                  labels={labels}
                  locale={locale}
                />
              </div>
            ) : flow === "account" ? (
              <div className="permission-account-choice">
                <label>
                  {text.chooseAccount}
                  <select
                    data-testid="permission-account"
                    value={draft.account_id}
                    onChange={(event) =>
                      edit({
                        ...draft,
                        account_id: event.target.value,
                        symbol_scope: "account",
                        symbols: [],
                      })
                    }
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
                <p>{text.accountWide}</p>
                <button
                  type="button"
                  className="permission-link"
                  data-testid="permission-advanced"
                  onClick={openAdvanced}
                >
                  {text.advanced}
                </button>
              </div>
            ) : review ? (
              <>
                <PermissionSummary
                  agentName={agent.name}
                  value={review.envelope}
                  accounts={accounts}
                  currency={currency}
                  text={text}
                  labels={labels}
                  locale={locale}
                  exact
                />
                <button
                  type="button"
                  className="permission-link"
                  data-testid="permission-advanced"
                  disabled={busy}
                  onClick={openAdvanced}
                >
                  {text.advanced}
                </button>
                {!supported && (
                  <p role="status" className="permission-notice">
                    {labels.unsupported}
                  </p>
                )}
                {enroll && (
                  <section className="permission-enrollment">
                    <label>
                      {labels.password}
                      <input
                        data-testid="permission-register-password"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      data-testid="permission-register"
                      disabled={!password || busy || !supported}
                      onClick={() =>
                        void execute(async () => {
                          const secret = password;
                          setPassword("");
                          const challenge = await api.post<DeviceChallenge>(
                            "/auth/devices/enrollment",
                            { password: secret, name: labels.device },
                          );
                          await api.post(
                            "/auth/devices/enrollment/verify",
                            await webDeviceProof(challenge, true),
                          );
                          if (alive()) {
                            setEnroll(false);
                            setError(undefined);
                          }
                        })
                      }
                    >
                      {labels.register}
                    </button>
                  </section>
                )}
              </>
            ) : (
              <p role="status">{text.expired}</p>
            )}
            {error != null && (
              <p className="permission-error" role="alert">
                {userError(error)}
              </p>
            )}
            {phase && (
              <p className="permission-notice" role="status">
                {text[phase]}
              </p>
            )}
            {!threadId && <p role="alert">{text.noThread}</p>}
          </div>
          <footer className="permission-dialog-footer">
            <div className="permission-save-state" role="status">
              {saved ? text.saved : flow === "editor" && !proposal ? text.invalid : ""}
            </div>
            <div className="permission-footer-buttons">
              <button
                type="button"
                data-testid="permission-cancel"
                className="permission-secondary"
                onClick={close}
              >
                {text.close}
              </button>
              {flow === "editor" || flow === "account" ? (
                <button
                  type="button"
                  className="permission-primary"
                  data-testid="permission-review-continue"
                  disabled={!proposal || busy || !threadId || agent.execution_mode === "shadow"}
                  onClick={() => void execute(async () => prepare(draftRef.current, true))}
                >
                  {busy ? text.preparing : text.continue}
                </button>
              ) : reviewPending ? (
                <button
                  type="button"
                  data-testid="permission-sign"
                  className="permission-primary"
                  disabled={!reviewPending || busy || !supported}
                  onClick={() =>
                    void execute(async () => {
                      if (!review) return;
                      const started = interaction.current;
                      setPhase("awaiting");
                      await activateAccountAuthority(api, review, async (challenge) => {
                        const proof = await webDeviceProof(challenge);
                        if (!alive() || interaction.current !== started)
                          throw Object.assign(new Error("device_authorization_cancelled"), {
                            code: "device_authorization_cancelled",
                          });
                        setPhase("verifying");
                        return proof;
                      });
                      const confirmed = await fresh();
                      if (
                        alive() &&
                        confirmed.effective_level === "autonomous" &&
                        confirmed.active_authorities.some((row) => row.id === review.id)
                      ) {
                        setPhase("activated");
                        setFlow(null);
                        setReview(null);
                        setPassword("");
                        setEnroll(false);
                      }
                    })
                  }
                >
                  {busy && phase ? text[phase] : text.sign}
                </button>
              ) : (
                <p
                  className="permission-explanation"
                  role="status"
                  data-testid="permission-review-state"
                >
                  {reviewActive ? text.activeAuthorization : text.expired}
                </p>
              )}
            </div>
          </footer>
        </DialogContent>
      </Dialog>
    </div>
  );
}
