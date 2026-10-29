import {
  type AccountAuthority,
  type Agent,
  type AgentPermissionLevel,
  type AuthorityDuration,
  authorityActions,
  type DeviceChallenge,
  type PermissionCustomization,
  type PermissionState,
  type Resource,
  type Thread,
} from "@lonora/contracts";
import {
  accountAuthorityLabels,
  activateAccountAuthority,
  authorityStatus,
  customizedManagementProposal,
  emptyManagementCustomization,
  numericalAuthorityLimits,
} from "@lonora/core";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  AppState,
  Keyboard,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { ApiError, api, SessionRequestCancelled } from "../lib/api";
import { brokerIdentityLabel } from "../lib/broker-identity";
import { deviceProof, deviceSupported } from "../lib/device-proof";
import { permissionLabels } from "../lib/permission-labels";
import { useSession } from "../lib/session";
import { SettingsGroup, SettingsRow, SettingsSwitch } from "./settings-group";
import { SheetHeader } from "./sheet-header";
import { colors, ErrorNotice, Field } from "./ui";

type Page = "select" | "editor" | "review";
type Group = "scope" | "operations" | "limits" | "duration";
type Signing = "preparing" | "confirming" | "verifying" | "activated" | "cancelled" | "failed";
type Props = { agent: Agent; threadId?: string; revision?: number; settings?: boolean };
const levels = ["analysis", "supervised", "autonomous"] as const;
const durations: AuthorityDuration[] = ["until_stopped", "12h", "24h", "7d"];

/** A native projection/editor of the existing server authority. Drafts grant nothing. */
export function AgentPermissions(props: Props) {
  const { owner, server } = useSession();
  if (!owner || props.agent.role === "delegated") return null;
  return <PermissionControl key={`${server}:${owner.id}:${props.agent.id}`} {...props} />;
}

function PermissionControl({ agent, threadId, revision = 0, settings = false }: Props) {
  const { rtl, t, errorText } = useSession();
  const copy = permissionLabels[rtl ? "ar" : "en"];
  const authorityCopy = accountAuthorityLabels[rtl ? "ar" : "en"];
  const [state, setState] = useState<PermissionState | null>(null);
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<Page>("select");
  const [selected, setSelected] = useState<AgentPermissionLevel>("analysis");
  const [expanded, setExpanded] = useState<Group | null>(null);
  const [draft, setDraft] = useState<PermissionCustomization>(() => initialDraft(agent));
  const [review, setReview] = useState<AccountAuthority | null>(null);
  const [connections, setConnections] = useState<Resource[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [currencies, setCurrencies] = useState<Record<string, string>>({});
  const [supported, setSupported] = useState(false);
  const [enroll, setEnroll] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signing, setSigning] = useState<Signing | null>(null);
  const [clock, setClock] = useState(Date.now());
  const current = useRef({ state, draft, dirty, errorText });
  current.current = { state, draft, dirty, errorText };
  const mounted = useRef(true);
  const loaded = useRef(false);
  const busyRef = useRef(false);
  const signingFlow = useRef(false);
  const saveRef = useRef<Promise<PermissionState> | null>(null);
  const editVersion = useRef(0);
  const baseRevision = useRef(0);
  const requestSequence = useRef(0);
  const appliedSequence = useRef(0);
  const path = `/agents/${encodeURIComponent(agent.id)}/permissions`;
  const validThread =
    threadId || threads.find((row) => row.agent_id === agent.id && !row.group_id)?.id || "";
  const specialist = agent.role !== "personal";
  const textStyle = {
    color: colors.foreground,
    textAlign: rtl ? ("right" as const) : ("left" as const),
    lineHeight: 22,
  };
  const rowDirection = rtl ? ("row-reverse" as const) : ("row" as const);
  const autonomyExpired =
    state?.effective_level === "autonomous" &&
    !state.active_authorities.some((row) => authorityStatus(row, clock) === "active");
  const effective = autonomyExpired ? state.fallback_level : (state?.effective_level ?? null);
  const effectiveStatus = autonomyExpired
    ? copy.authorization_expired
    : state &&
        ["awaiting_authorization", "authorization_expired", "autonomous_stopped"].includes(
          state.status,
        )
      ? copy[
          state.status as "awaiting_authorization" | "authorization_expired" | "autonomous_stopped"
        ]
      : null;

  const accept = useCallback(
    (next: PermissionState, forceDraft = false) => {
      if (
        !mounted.current ||
        next.agent_id !== agent.id ||
        next.revision < (current.current.state?.revision ?? 0)
      )
        return;
      const previousRevision = current.current.state?.revision;
      current.current.state = next;
      setState(next);
      if (forceDraft || !loaded.current || !current.current.dirty) {
        setDraft(next.customization ? cloneDraft(next.customization) : initialDraft(agent));
        baseRevision.current = next.revision;
        setDirty(false);
        setConflict(false);
      }
      if (
        !loaded.current ||
        !open ||
        (!busyRef.current && !current.current.dirty && previousRevision !== next.revision)
      )
        setSelected(next.requested_level);
      loaded.current = true;
      setReview((existing) =>
        existing && next.pending_authority?.id !== existing.id ? null : existing,
      );
    },
    [agent, open],
  );
  const acceptRef = useRef(accept);
  acceptRef.current = accept;
  const refresh = useCallback(
    async (forceDraft = false) => {
      const sequence = ++requestSequence.current;
      const next = await api.get<PermissionState>(path);
      if (mounted.current && sequence >= appliedSequence.current) {
        appliedSequence.current = sequence;
        acceptRef.current(next, forceDraft);
      }
      return next;
    },
    [path],
  );
  const report = useCallback((cause: unknown) => {
    if (mounted.current && !(cause instanceof SessionRequestCancelled)) {
      setError(current.current.errorText(cause));
      if (cause instanceof ApiError && cause.code === "version_conflict") setConflict(true);
    }
  }, []);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    void revision;
    void refresh().catch(report);
  }, [refresh, report, revision]);
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (value) => {
      if (value === "active") void refresh().catch(report);
    });
    return () => subscription.remove();
  }, [refresh, report]);
  useEffect(() => {
    if (!open) return;
    let live = true;
    void Promise.allSettled([
      api.get<Resource[]>("/trading/connections"),
      threadId
        ? Promise.resolve([] as Thread[])
        : api.get<Thread[]>(`/threads?agent_id=${encodeURIComponent(agent.id)}`),
      Promise.all([
        deviceSupported(),
        api.get<{ android_configured: boolean; ios_configured: boolean }>("/auth/devices/config"),
      ]),
    ])
      .then(([accounts, conversations, device]) => {
        if (!live) return;
        if (accounts.status === "fulfilled")
          setConnections(accounts.value.filter((row) => row.payload.enabled === true));
        else report(accounts.reason);
        if (conversations.status === "fulfilled")
          setThreads(
            conversations.value.filter((row) => row.agent_id === agent.id && !row.group_id),
          );
        else report(conversations.reason);
        if (device.status === "fulfilled") {
          const [local, config] = device.value;
          setSupported(
            Boolean(local) &&
              (Platform.OS === "web" ||
                (Platform.OS === "android" ? config.android_configured : config.ios_configured)),
          );
        } else setSupported(false);
      })
      .catch(report);
    const timer = setInterval(() => {
      if (AppState.currentState === "active") void refresh().catch(report);
    }, 15000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [open, agent.id, threadId, refresh, report]);
  useEffect(() => {
    const expirations = [state?.pending_authority, ...(state?.active_authorities ?? [])]
      .flatMap((row) =>
        row ? [row.status === "pending" ? row.activation_expires_at : null, row.valid_until] : [],
      )
      .filter((value): value is string => Boolean(value))
      .map(Date.parse)
      .filter((value) => Number.isFinite(value) && value > Date.now());
    if (!expirations.length) return;
    const timer = setTimeout(
      () => {
        setClock(Date.now());
        void refresh().catch(report);
      },
      Math.min(Math.max(0, Math.min(...expirations) - Date.now() + 30), 2147483647),
    );
    return () => clearTimeout(timer);
  }, [state, refresh, report]);
  const accountId = page === "review" && review ? review.account_id : draft.account_id;
  useEffect(() => {
    if (!open || !accountId) return;
    let live = true;
    void api
      .get<{ account: { currency: string } }>(`/trading/accounts/${encodeURIComponent(accountId)}`)
      .then((result) => {
        if (live && result.account.currency)
          setCurrencies((value) => ({ ...value, [accountId]: result.account.currency }));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [open, accountId]);
  useEffect(() => {
    setSymbols([]);
    setQuery("");
    if (
      !open ||
      page !== "editor" ||
      !draft.account_id ||
      specialist ||
      draft.symbol_scope === "account"
    )
      return;
    let live = true;
    void api
      .get<string[]>(`/market/symbols?account_id=${encodeURIComponent(draft.account_id)}`)
      .then((values) => {
        if (live) setSymbols(values);
      })
      .catch(report);
    return () => {
      live = false;
    };
  }, [open, page, draft.account_id, draft.symbol_scope, specialist, report]);

  const updateDraft = (change: Partial<PermissionCustomization>) => {
    if (busyRef.current || conflict) return;
    if (!current.current.dirty) baseRevision.current = current.current.state?.revision ?? 0;
    editVersion.current += 1;
    const value = { ...current.current.draft, ...change };
    current.current.draft = value;
    current.current.dirty = true;
    setDraft(value);
    setDirty(true);
    setError(null);
  };
  const saveDraft = useCallback(async (): Promise<PermissionState> => {
    if (saveRef.current) {
      await saveRef.current;
      return current.current.dirty ? saveDraft() : (current.current.state as PermissionState);
    }
    if (!current.current.state) throw new Error("permission_state_unavailable");
    if (!current.current.dirty) return current.current.state;
    const version = editVersion.current;
    const body = cloneDraft(current.current.draft);
    setSaving(true);
    const request = api.put<PermissionState>(`${path}/customization`, {
      expected_revision: baseRevision.current,
      customization: body,
    });
    saveRef.current = request;
    try {
      const next = await request;
      if (mounted.current) {
        if (next.revision < (current.current.state?.revision ?? 0)) {
          setConflict(true);
          throw new ApiError("version_conflict", 409);
        }
        setState(next);
        current.current.state = next;
        baseRevision.current = next.revision;
        if (editVersion.current === version) {
          current.current.dirty = false;
          setDirty(false);
          setConflict(false);
        }
      }
      return next;
    } finally {
      saveRef.current = null;
      if (mounted.current) setSaving(false);
    }
  }, [path]);
  useEffect(() => {
    // Incomplete preferences are safe to persist: only a valid, signed proposal
    // can grant authority. Restart the debounce whenever the draft changes.
    void draft;
    if (!dirty || busy || conflict) return;
    const timer = setTimeout(() => {
      void saveDraft().catch(report);
    }, 650);
    return () => clearTimeout(timer);
  }, [dirty, draft, busy, conflict, saveDraft, report]);

  const execute = async (operation: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      await operation();
    } catch (cause) {
      report(cause);
      if (cause instanceof ApiError && cause.code === "device_registration_required")
        setEnroll(true);
      if (signingFlow.current) {
        const canceled =
          cause instanceof Error &&
          /cancel|NotAllowedError|AbortError/i.test(`${cause.name} ${cause.message}`);
        setSigning(canceled ? "cancelled" : "failed");
      }
    } finally {
      busyRef.current = false;
      signingFlow.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  const prepare = async () => {
    signingFlow.current = true;
    Keyboard.dismiss();
    setSigning("preparing");
    const latest = await saveDraft();
    let conversation = validThread;
    if (!conversation) {
      const conversations = await api.get<Thread[]>(
        `/threads?agent_id=${encodeURIComponent(agent.id)}`,
      );
      conversation =
        conversations.find((row) => row.agent_id === agent.id && !row.group_id)?.id ?? "";
      if (mounted.current) setThreads(conversations);
    }
    if (!mounted.current) throw new SessionRequestCancelled();
    const body = customizedManagementProposal(current.current.draft, {
      thread_id: conversation,
      account_id: current.current.draft.account_id,
      symbol_scope: current.current.draft.symbol_scope,
      symbols: current.current.draft.symbols,
    });
    if (!body) throw new Error("invalid_authority_proposal");
    const pending = await api.post<AccountAuthority>(
      `/agents/${encodeURIComponent(agent.id)}/account-authorities?permission_revision=${latest.revision}`,
      body,
    );
    const next = await refresh();
    if (mounted.current && next.pending_authority?.id === pending.id) {
      setReview(pending);
      setPage("review");
      setSigning(null);
      setEnroll(false);
    } else if (mounted.current) throw new ApiError("version_conflict", 409);
  };
  const choose = (level: AgentPermissionLevel) => {
    setSelected(level);
    setSigning(null);
    if (level === "autonomous") {
      if (state?.pending_authority && authorityStatus(state.pending_authority) === "pending") {
        setReview(state.pending_authority);
        setPage("review");
      } else if (effective !== "autonomous") {
        if (draft.account_id) void execute(prepare);
        else {
          setPage("editor");
          setExpanded(null);
        }
      }
      return;
    }
    void execute(async () => {
      // Finish an in-flight preference save first. It cannot re-enable financial authority.
      if (saveRef.current) await saveRef.current;
      const latest = await refresh();
      const next = await api.put<PermissionState>(path, {
        level,
        expected_revision: latest.revision,
      });
      if (mounted.current) {
        acceptRef.current(next);
        baseRevision.current = current.current.state?.revision ?? next.revision;
        setSelected(current.current.state?.requested_level ?? level);
        setReview(null);
        setSigning(null);
      }
    });
  };
  const close = () => {
    if (busyRef.current) return;
    Keyboard.dismiss();
    if (page !== "select") {
      setPage("select");
      setPassword("");
      setEnroll(false);
    } else {
      setOpen(false);
      setPassword("");
    }
  };
  const openControl = () => {
    Keyboard.dismiss();
    setOpen(true);
    setPage("select");
    setSelected(state?.requested_level ?? "analysis");
    setSigning(null);
    void refresh().catch(report);
  };
  const accountName = (id: string) => {
    const index = connections.findIndex((row) => row.id === id);
    return index < 0 ? authorityCopy.account : brokerIdentityLabel(connections[index], index, t);
  };
  const expiry = (value: string | null) =>
    value
      ? `${new Date(value).toLocaleString(rtl ? "ar" : "en", { timeZoneName: "short" })}\n${value}`
      : copy.until_stopped;
  const proposal = customizedManagementProposal(draft, {
    thread_id: validThread,
    account_id: draft.account_id,
    symbol_scope: draft.symbol_scope,
    symbols: draft.symbols,
  });
  const scopeSummary = draft.account_id
    ? `${accountName(draft.account_id)} · ${draft.symbol_scope === "account" ? copy.accountScope : draft.symbols.join(", ")}`
    : authorityCopy.account;
  const limitSummary =
    numericalAuthorityLimits
      .filter((field) => draft.limits[field] !== "")
      .map(
        (field) =>
          `${authorityCopy[field]}: ${draft.limits[field]}${field === "minimum_equity" ? ` ${currencies[draft.account_id] ?? copy.currencyUnknown}` : ""}`,
      )
      .join(" · ") || copy.unlimited;
  const groupSummary = {
    scope: scopeSummary,
    operations: `${draft.actions.length}/${authorityActions.length} ${copy.selected}`,
    limits: limitSummary,
    duration: `${copy[draft.duration]} · ${draft.allow_manual_positions ? copy.manualYes : copy.manualNo}`,
  };
  const readyToSign =
    review !== null &&
    authorityStatus(review, clock) === "pending" &&
    state?.pending_authority?.id === review.id;
  const section = (name: Group, children: ReactNode) => (
    <View
      key={name}
      style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 16, overflow: "hidden" }}
    >
      <Pressable
        testID={`permission-group-${name}`}
        accessibilityRole="button"
        accessibilityLabel={copy[name]}
        accessibilityHint={copy.groupHint}
        aria-expanded={expanded === name}
        accessibilityState={{ expanded: expanded === name, disabled: busy }}
        disabled={busy}
        onPress={() => setExpanded((value) => (value === name ? null : name))}
        style={{ padding: 14, minHeight: 64, gap: 5 }}
      >
        <Text style={{ ...textStyle, fontWeight: "600" }}>
          {copy[name]} {expanded === name ? "−" : "+"}
        </Text>
        <Text numberOfLines={3} style={{ ...textStyle, color: colors.secondary, fontSize: 13 }}>
          {groupSummary[name]}
        </Text>
      </Pressable>
      {expanded === name && <View style={{ padding: 14, paddingTop: 0, gap: 12 }}>{children}</View>}
    </View>
  );
  const actionButton = (
    label: string,
    onPress: () => void,
    id?: string,
    disabled = false,
    secondary = false,
  ) => (
    <Pressable
      testID={id}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => ({
        minHeight: 46,
        paddingHorizontal: 14,
        paddingVertical: 12,
        borderRadius: 14,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: secondary ? colors.muted : colors.primary,
        opacity: disabled || pressed ? 0.45 : 1,
      })}
    >
      <Text
        style={{
          ...textStyle,
          fontWeight: "600",
          color: secondary ? colors.foreground : colors.primaryForeground,
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
  const summary = (exact?: AccountAuthority) => {
    const envelope = exact?.envelope;
    const chosenAccount = exact?.account_id ?? draft.account_id;
    const currency = currencies[chosenAccount] ?? copy.currencyUnknown;
    return (
      <View
        testID={exact ? "permission-exact-scope-native" : "permission-summary-native"}
        style={{ gap: 8, padding: 14, backgroundColor: colors.muted, borderRadius: 16 }}
      >
        <Text accessibilityRole="header" style={{ ...textStyle, fontWeight: "600" }}>
          {copy.summary}
        </Text>
        <Text style={textStyle}>{agent.name}</Text>
        <Text style={textStyle}>{accountName(chosenAccount)}</Text>
        <Text style={textStyle}>
          {(envelope?.symbol_scope ?? draft.symbol_scope) === "account"
            ? copy.accountScope
            : (envelope?.symbols ?? draft.symbols).join(", ")}
        </Text>
        <Text style={textStyle}>
          {(envelope?.actions ?? draft.actions).map((action) => authorityCopy[action]).join(" · ")}
        </Text>
        {exact ? (
          numericalAuthorityLimits.map((field) =>
            exact.envelope[field] === null ? null : (
              <Text key={field} style={textStyle}>
                {authorityCopy[field]}: {String(exact.envelope[field])}
                {field === "minimum_equity" ? ` ${currency}` : ""}
              </Text>
            ),
          )
        ) : (
          <Text style={textStyle}>{limitSummary}</Text>
        )}
        {exact && numericalAuthorityLimits.every((field) => exact.envelope[field] === null) && (
          <Text style={textStyle}>{copy.unlimited}</Text>
        )}
        <Text style={textStyle}>{exact ? expiry(exact.valid_until) : copy[draft.duration]}</Text>
        <Text style={textStyle}>
          {(envelope?.allow_manual_positions ?? draft.allow_manual_positions)
            ? copy.manualYes
            : copy.manualNo}
        </Text>
        <Text style={textStyle}>{copy.noApproval}</Text>
        <Text style={{ ...textStyle, color: colors.warning, fontSize: 13 }}>{copy.risk}</Text>
      </View>
    );
  };
  const notice = (
    <>
      <ErrorNotice text={error} />
      {conflict &&
        actionButton(
          copy.reload,
          () => {
            void refresh(true)
              .then(() => setError(null))
              .catch(report);
          },
          "permission-reload-native",
          busy,
          true,
        )}
      {signing && (
        <Text
          accessibilityLiveRegion="polite"
          style={{ ...textStyle, color: signing === "failed" ? colors.error : colors.secondary }}
        >
          {copy[signing]}
        </Text>
      )}
    </>
  );
  return (
    <>
      {settings ? (
        <SettingsGroup>
          <SettingsRow
            title={copy.title}
            value={effective ? copy[effective] : copy.unavailable}
            onPress={openControl}
          />
        </SettingsGroup>
      ) : (
        <View style={{ alignItems: rtl ? "flex-end" : "flex-start" }}>
          <Pressable
            testID="permission-selector-native"
            hitSlop={6}
            accessibilityRole="button"
            aria-expanded={open}
            accessibilityLabel={`${copy.title}: ${effective ? copy[effective] : copy.unavailable}`}
            accessibilityState={{ expanded: open }}
            onPress={openControl}
            style={{
              minHeight: 36,
              maxWidth: "100%",
              paddingHorizontal: 12,
              paddingVertical: 8,
              borderRadius: 18,
              borderWidth: 1,
              borderColor: colors.border,
              flexDirection: rowDirection,
              gap: 6,
              alignItems: "center",
            }}
          >
            <Text numberOfLines={1} style={{ ...textStyle, fontSize: 12, flexShrink: 1 }}>
              {effective ? copy[effective] : copy.title}
            </Text>
            <Text style={{ color: colors.secondary }}>⌄</Text>
          </Pressable>
        </View>
      )}
      <Modal
        visible={open}
        transparent
        animationType="slide"
        onRequestClose={close}
        presentationStyle="overFullScreen"
        statusBarTranslucent
      >
        {page === "select" ? (
          <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={copy.close}
              onPress={close}
              style={{ flex: 1 }}
            />
            <SafeAreaView
              testID="permission-sheet-native"
              edges={["bottom", "left", "right"]}
              style={{
                maxHeight: "90%",
                backgroundColor: colors.background,
                borderTopLeftRadius: 24,
                borderTopRightRadius: 24,
              }}
            >
              <SheetHeader title={copy.title} onClose={close} />
              <ScrollView
                contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 18, gap: 10 }}
                keyboardShouldPersistTaps="handled"
              >
                <Text
                  testID="permission-effective-native"
                  accessibilityLiveRegion="polite"
                  style={{ ...textStyle, color: colors.secondary }}
                >
                  {copy.effective}: {effective ? copy[effective] : copy.unavailable}
                </Text>
                {effectiveStatus && (
                  <Text style={{ ...textStyle, color: colors.warning }}>{effectiveStatus}</Text>
                )}
                {!state
                  ? actionButton(
                      copy.retry,
                      () => {
                        void refresh().catch(report);
                      },
                      undefined,
                      busy,
                      true,
                    )
                  : levels.map((level) => (
                      <Pressable
                        key={level}
                        testID={`permission-choice-${level}`}
                        accessibilityRole="radio"
                        accessibilityLabel={copy[level]}
                        aria-checked={selected === level}
                        accessibilityState={{
                          checked: selected === level,
                          selected: selected === level,
                          disabled: busy,
                        }}
                        disabled={busy}
                        onPress={() => choose(level)}
                        style={{
                          minHeight: 68,
                          padding: 12,
                          borderRadius: 14,
                          backgroundColor: selected === level ? colors.accent : colors.muted,
                          flexDirection: rowDirection,
                          alignItems: "center",
                          gap: 12,
                          opacity: busy ? 0.5 : 1,
                        }}
                      >
                        <Text style={{ color: colors.foreground }}>
                          {selected === level ? "●" : "○"}
                        </Text>
                        <View style={{ flex: 1, gap: 4 }}>
                          <Text style={{ ...textStyle, fontWeight: "600" }}>{copy[level]}</Text>
                          <Text style={{ ...textStyle, fontSize: 13, color: colors.secondary }}>
                            {copy[`${level}Hint`]}
                          </Text>
                        </View>
                      </Pressable>
                    ))}
                {selected === "autonomous" &&
                  actionButton(
                    copy.advanced,
                    () => {
                      setPage("editor");
                      setExpanded(null);
                      setSigning(null);
                    },
                    "permission-advanced-native",
                    busy || !state,
                    true,
                  )}
                {state?.pending_authority &&
                  selected === "autonomous" &&
                  actionButton(
                    authorityCopy.review,
                    () => {
                      setReview(state.pending_authority);
                      setPage("review");
                    },
                    "permission-open-review-native",
                    busy,
                    true,
                  )}
                {notice}
              </ScrollView>
            </SafeAreaView>
          </View>
        ) : (
          <SafeAreaView
            edges={["top", "bottom", "left", "right"]}
            style={{ flex: 1, backgroundColor: colors.background }}
          >
            <KeyboardAvoidingView
              behavior={Platform.OS === "ios" ? "padding" : "height"}
              style={{ flex: 1 }}
            >
              <View
                testID={page === "editor" ? "permission-editor-native" : "permission-review-native"}
                style={{ flex: 1 }}
              >
                <SheetHeader
                  title={page === "editor" ? copy.advanced : authorityCopy.review}
                  onClose={close}
                />
                <Text
                  numberOfLines={1}
                  style={{
                    ...textStyle,
                    paddingHorizontal: 20,
                    paddingBottom: 10,
                    color: colors.secondary,
                  }}
                >
                  {agent.name}
                </Text>
                <ScrollView
                  contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 18, gap: 12 }}
                  keyboardShouldPersistTaps="handled"
                  keyboardDismissMode="on-drag"
                >
                  <Text
                    testID="permission-effective-native"
                    accessibilityLiveRegion="polite"
                    style={{ ...textStyle, color: colors.secondary }}
                  >
                    {copy.effective}: {effective ? copy[effective] : copy.unavailable}
                  </Text>
                  {effectiveStatus && (
                    <Text style={{ ...textStyle, color: colors.warning }}>{effectiveStatus}</Text>
                  )}
                  {page === "editor" ? (
                    <>
                      {section(
                        "scope",
                        specialist ? (
                          <Text style={textStyle}>
                            {accountName(agent.trading_account_id ?? "")} · {agent.trading_symbol}
                          </Text>
                        ) : (
                          <>
                            {!connections.length && (
                              <Text style={textStyle}>{copy.noAccounts}</Text>
                            )}
                            {connections.map((account) => (
                              <Pressable
                                key={account.id}
                                testID={`permission-account-${account.id}-native`}
                                accessibilityRole="radio"
                                accessibilityLabel={accountName(account.id)}
                                accessibilityState={{
                                  selected: draft.account_id === account.id,
                                  disabled: busy,
                                }}
                                disabled={busy}
                                onPress={() =>
                                  updateDraft({
                                    account_id: account.id,
                                    symbols: [],
                                    symbol_scope: "selected",
                                  })
                                }
                                style={{
                                  minHeight: 48,
                                  padding: 10,
                                  borderRadius: 12,
                                  backgroundColor:
                                    draft.account_id === account.id ? colors.accent : colors.muted,
                                }}
                              >
                                <Text style={textStyle}>
                                  {draft.account_id === account.id ? "● " : "○ "}
                                  {accountName(account.id)}
                                </Text>
                              </Pressable>
                            ))}
                            <SettingsSwitch
                              label={copy.accountScope}
                              value={draft.symbol_scope === "account"}
                              disabled={busy || !draft.account_id || conflict}
                              onChange={(enabled) =>
                                updateDraft({
                                  symbol_scope: enabled ? "account" : "selected",
                                  symbols: [],
                                })
                              }
                            />
                            {draft.symbol_scope === "selected" && (
                              <>
                                <Field
                                  label={t("searchBrokerSymbols")}
                                  value={query}
                                  editable={!busy && Boolean(draft.account_id)}
                                  onChangeText={setQuery}
                                  autoCapitalize="none"
                                />
                                <View
                                  style={{
                                    flexDirection: rowDirection,
                                    flexWrap: "wrap",
                                    gap: 8,
                                  }}
                                >
                                  {draft.symbols.map((symbol) => (
                                    <Pressable
                                      key={symbol}
                                      accessibilityRole="button"
                                      accessibilityLabel={`${authorityCopy.remove ?? copy.none}: ${symbol}`}
                                      disabled={busy || conflict}
                                      onPress={() =>
                                        updateDraft({
                                          symbols: draft.symbols.filter(
                                            (value) => value !== symbol,
                                          ),
                                        })
                                      }
                                      style={{
                                        minHeight: 44,
                                        padding: 10,
                                        borderRadius: 12,
                                        backgroundColor: colors.accent,
                                      }}
                                    >
                                      <Text style={textStyle}>{symbol} ×</Text>
                                    </Pressable>
                                  ))}
                                </View>
                                {symbols
                                  .filter(
                                    (value) =>
                                      !draft.symbols.includes(value) &&
                                      value.toLowerCase().includes(query.toLowerCase()),
                                  )
                                  .slice(0, 20)
                                  .map((symbol) => (
                                    <Pressable
                                      key={symbol}
                                      accessibilityRole="button"
                                      accessibilityLabel={symbol}
                                      disabled={busy || conflict || draft.symbols.length >= 100}
                                      onPress={() =>
                                        updateDraft({ symbols: [...draft.symbols, symbol] })
                                      }
                                      style={{
                                        minHeight: 44,
                                        padding: 10,
                                        borderBottomWidth: 1,
                                        borderColor: colors.border,
                                      }}
                                    >
                                      <Text style={textStyle}>{symbol}</Text>
                                    </Pressable>
                                  ))}
                              </>
                            )}
                          </>
                        ),
                      )}
                      {section(
                        "operations",
                        <>
                          <View style={{ flexDirection: rowDirection, gap: 10 }}>
                            <View style={{ flex: 1 }}>
                              {actionButton(
                                copy.all,
                                () => updateDraft({ actions: [...authorityActions] }),
                                "permission-actions-all-native",
                                busy || conflict,
                                true,
                              )}
                            </View>
                            <View style={{ flex: 1 }}>
                              {actionButton(
                                copy.none,
                                () => updateDraft({ actions: [] }),
                                "permission-actions-none-native",
                                busy || conflict,
                                true,
                              )}
                            </View>
                          </View>
                          <View style={{ flexDirection: rowDirection, flexWrap: "wrap", gap: 8 }}>
                            {authorityActions.map((action) => (
                              <Pressable
                                key={action}
                                testID={`permission-action-${action}-native`}
                                accessibilityRole="checkbox"
                                accessibilityLabel={authorityCopy[action]}
                                accessibilityState={{
                                  checked: draft.actions.includes(action),
                                  disabled: busy || conflict,
                                }}
                                disabled={busy || conflict}
                                onPress={() =>
                                  updateDraft({
                                    actions: draft.actions.includes(action)
                                      ? draft.actions.filter((value) => value !== action)
                                      : [...draft.actions, action],
                                  })
                                }
                                style={{
                                  minHeight: 44,
                                  padding: 10,
                                  borderRadius: 12,
                                  borderWidth: 1,
                                  borderColor: colors.border,
                                  backgroundColor: draft.actions.includes(action)
                                    ? colors.accent
                                    : colors.background,
                                  maxWidth: "100%",
                                }}
                              >
                                <Text style={textStyle}>
                                  {draft.actions.includes(action) ? "✓ " : ""}
                                  {authorityCopy[action]}
                                </Text>
                              </Pressable>
                            ))}
                          </View>
                        </>,
                      )}
                      {section(
                        "limits",
                        numericalAuthorityLimits.map((field) => (
                          <Field
                            key={field}
                            testID={`permission-limit-${field}-native`}
                            label={`${authorityCopy[field]}${field === "minimum_equity" ? ` · ${currencies[draft.account_id] ?? copy.currencyUnknown}` : ""}`}
                            value={draft.limits[field]}
                            maxLength={80}
                            placeholder={copy.optional}
                            editable={!busy && !conflict}
                            keyboardType={
                              [
                                "maximum_positions",
                                "maximum_pending_orders",
                                "maximum_actions",
                              ].includes(field)
                                ? "number-pad"
                                : "decimal-pad"
                            }
                            autoCapitalize="none"
                            onChangeText={(value) =>
                              updateDraft({ limits: { ...draft.limits, [field]: value } })
                            }
                          />
                        )),
                      )}
                      {section(
                        "duration",
                        <>
                          <View style={{ flexDirection: rowDirection, flexWrap: "wrap", gap: 8 }}>
                            {durations.map((duration) => (
                              <Pressable
                                key={duration}
                                testID={`permission-duration-${duration}-native`}
                                accessibilityRole="radio"
                                accessibilityLabel={copy[duration]}
                                accessibilityState={{
                                  selected: draft.duration === duration,
                                  disabled: busy || conflict,
                                }}
                                disabled={busy || conflict}
                                onPress={() => updateDraft({ duration })}
                                style={{
                                  minHeight: 44,
                                  padding: 12,
                                  borderRadius: 12,
                                  backgroundColor:
                                    draft.duration === duration ? colors.accent : colors.muted,
                                }}
                              >
                                <Text style={textStyle}>{copy[duration]}</Text>
                              </Pressable>
                            ))}
                          </View>
                          <SettingsSwitch
                            label={authorityCopy.manual}
                            value={draft.allow_manual_positions}
                            disabled={busy || conflict}
                            onChange={(value) => updateDraft({ allow_manual_positions: value })}
                          />
                        </>,
                      )}
                      {summary()}
                      {!validThread && (
                        <Text style={{ ...textStyle, color: colors.warning }}>{copy.noThread}</Text>
                      )}
                      {!proposal && (
                        <Text style={{ ...textStyle, color: colors.warning }}>{copy.invalid}</Text>
                      )}
                      <Text
                        accessibilityLiveRegion="polite"
                        style={{ ...textStyle, color: colors.secondary, fontSize: 13 }}
                      >
                        {saving ? copy.saving : dirty ? copy.unsaved : copy.saved}
                      </Text>
                    </>
                  ) : review ? (
                    <>
                      <Text style={textStyle}>{copy.signHint}</Text>
                      {summary(review)}
                      {!readyToSign && (
                        <Text style={{ ...textStyle, color: colors.warning }}>
                          {copy.authorization_expired}
                        </Text>
                      )}
                      {!supported && (
                        <Text style={{ ...textStyle, color: colors.warning }}>
                          {copy.signingUnsupported}
                        </Text>
                      )}
                      {enroll && (
                        <>
                          <Field
                            label={authorityCopy.password}
                            secureTextEntry
                            autoComplete="current-password"
                            value={password}
                            onChangeText={setPassword}
                            editable={!busy}
                          />
                          {actionButton(
                            authorityCopy.register,
                            () => {
                              void execute(async () => {
                                const secret = password;
                                setPassword("");
                                const challenge = await api.post<DeviceChallenge>(
                                  "/auth/devices/enrollment",
                                  { password: secret, name: authorityCopy.device },
                                );
                                await api.post(
                                  "/auth/devices/enrollment/verify",
                                  await deviceProof(challenge, true),
                                );
                                if (mounted.current) {
                                  setEnroll(false);
                                  setSigning(null);
                                }
                              });
                            },
                            "permission-enroll-native",
                            busy || !password || !supported,
                          )}
                        </>
                      )}
                      {actionButton(
                        copy.advanced,
                        () => {
                          setPage("editor");
                          setExpanded(null);
                          setPassword("");
                          setEnroll(false);
                          setSigning(null);
                        },
                        "permission-review-advanced-native",
                        busy,
                        true,
                      )}
                      {actionButton(
                        copy.cancelRequest,
                        () => {
                          void execute(async () => {
                            await api.post(
                              `/account-authorities/${encodeURIComponent(review.id)}/revoke`,
                              {},
                            );
                            await refresh();
                            if (mounted.current) {
                              setReview(null);
                              setPage("select");
                              setSigning("cancelled");
                              setPassword("");
                              setEnroll(false);
                            }
                          });
                        },
                        "permission-cancel-native",
                        busy || !readyToSign,
                        true,
                      )}
                    </>
                  ) : (
                    <Text style={textStyle}>{copy.unavailable}</Text>
                  )}
                  {notice}
                </ScrollView>
                <View
                  style={{
                    padding: 16,
                    borderTopWidth: 1,
                    borderColor: colors.border,
                    gap: 8,
                    backgroundColor: colors.background,
                  }}
                >
                  {busy && (
                    <ActivityIndicator
                      accessibilityLabel={page === "editor" ? copy.preparing : copy.verifying}
                      color={colors.secondary}
                    />
                  )}
                  {page === "editor"
                    ? actionButton(
                        copy.review,
                        () => {
                          void execute(prepare);
                        },
                        "permission-review-continue-native",
                        busy ||
                          !proposal ||
                          conflict ||
                          !state ||
                          agent.execution_mode === "shadow" ||
                          agent.paused,
                      )
                    : actionButton(
                        copy.sign,
                        () => {
                          if (!review) return;
                          void execute(async () => {
                            signingFlow.current = true;
                            setSigning("preparing");
                            await activateAccountAuthority(api, review, async (challenge) => {
                              setSigning("confirming");
                              const proof = await deviceProof(challenge);
                              if (!mounted.current) throw new SessionRequestCancelled();
                              if (mounted.current) setSigning("verifying");
                              return proof;
                            });
                            const next = await refresh();
                            if (next.effective_level !== "autonomous")
                              throw new Error("account_authority_activation_unconfirmed");
                            if (mounted.current) {
                              setSelected("autonomous");
                              setReview(null);
                              setPage("select");
                              setSigning("activated");
                              setPassword("");
                            }
                          });
                        },
                        "permission-sign-native",
                        busy || !readyToSign || !supported || enroll,
                      )}
                </View>
              </View>
            </KeyboardAvoidingView>
          </SafeAreaView>
        )}
      </Modal>
    </>
  );
}

function initialDraft(agent: Agent): PermissionCustomization {
  const personal = agent.role === "personal";
  return {
    ...emptyManagementCustomization(),
    account_id: personal ? "" : (agent.trading_account_id ?? ""),
    symbol_scope: personal || agent.trading_symbol ? "selected" : "account",
    symbols: !personal && agent.trading_symbol ? [agent.trading_symbol] : [],
  };
}
function cloneDraft(value: PermissionCustomization): PermissionCustomization {
  return {
    ...value,
    symbols: [...value.symbols],
    actions: [...value.actions],
    limits: { ...value.limits },
  };
}
