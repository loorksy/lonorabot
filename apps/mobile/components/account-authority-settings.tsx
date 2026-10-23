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
} from "@lonora/core";
import { useEffect, useRef, useState } from "react";
import { AppState, Modal, Platform, ScrollView, Text, View } from "react-native";
import { ApiError, api, SessionRequestCancelled } from "../lib/api";
import { brokerIdentityLabel } from "../lib/broker-identity";
import { deviceProof, deviceSupported } from "../lib/device-proof";
import { useSession } from "../lib/session";
import { type BrokerPair, BrokerPairPicker } from "./broker-pair-picker";
import { SettingsGroup, SettingsRow, SettingsSwitch } from "./settings-group";
import { SheetHeader } from "./sheet-header";
import { Button, colors, ErrorNotice, Field } from "./ui";

/** Same immutable signed account scope as Web, never a local autonomy toggle. */
export function AccountAuthoritySettings({ agent }: { agent: Agent }) {
  const { owner, server, rtl, t, errorText } = useSession();
  const text = accountAuthorityLabels[rtl ? "ar" : "en"];
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
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
  const [review, setReview] = useState<AccountAuthority | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [supported, setSupported] = useState(false);
  const [enroll, setEnroll] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const scope = `${server}:${owner?.id}:${agent.id}`;
  const current = useRef(scope);
  current.current = scope;
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    void tick;
    if (!owner) return;
    let active = true;
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
        if (active && !(cause instanceof SessionRequestCancelled)) setError(errorText(cause));
      });
    return () => {
      active = false;
    };
  }, [agent.id, owner, tick, errorText]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    const check = async () => {
      try {
        const [local, config] = await Promise.all([
          deviceSupported(),
          api.get<{ android_configured: boolean; ios_configured: boolean }>("/auth/devices/config"),
        ]);
        if (active)
          setSupported(
            Boolean(local) &&
              (Platform.OS === "web" ||
                (Platform.OS === "android" ? config.android_configured : config.ios_configured)),
          );
      } catch {
        if (active) setSupported(false);
      }
    };
    void check();
    const listener = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        void check();
        setTick((value) => value + 1);
      }
    });
    const timer = setInterval(() => {
      if (AppState.currentState === "active") setTick((value) => value + 1);
    }, 15000);
    return () => {
      active = false;
      listener.remove();
      clearInterval(timer);
    };
  }, [open]);
  const execute = async (operation: () => Promise<void>) => {
    if (busy) return;
    const started = scope;
    setBusy(true);
    setError(null);
    try {
      await operation();
    } catch (cause) {
      if (
        alive.current &&
        current.current === started &&
        !(cause instanceof SessionRequestCancelled)
      ) {
        setError(errorText(cause));
        if (cause instanceof ApiError && cause.code === "device_registration_required")
          setEnroll(true);
      }
    } finally {
      if (alive.current && current.current === started) {
        setBusy(false);
        setTick((value) => value + 1);
      }
    }
  };
  const accountName = (id: string) => {
    const index = connections.findIndex((row) => row.id === id);
    return index >= 0 ? brokerIdentityLabel(connections[index], index, t) : text.account;
  };
  const proposal = authorityProposal(draft, {
    thread_id: threadId || (threads.length === 1 ? threads[0].id : ""),
    account_id: pair.trading_account_id,
    symbols,
    actions,
    allow_manual_positions: manual,
  });
  const style = {
    color: colors.foreground,
    textAlign: rtl ? ("right" as const) : ("left" as const),
    lineHeight: 22,
  };
  const close = () => {
    if (!busy) {
      setOpen(false);
      setReview(null);
      setPassword("");
      setEnroll(false);
    }
  };
  if (agent.role === "delegated") return null;
  return (
    <>
      <SettingsGroup>
        <SettingsRow
          title={text.title}
          value={rows.some((row) => authorityStatus(row) === "active") ? text.active : text.off}
          onPress={() => {
            setOpen(true);
            setTick((value) => value + 1);
          }}
        />
      </SettingsGroup>
      <Modal
        visible={open}
        animationType="slide"
        onRequestClose={close}
        presentationStyle="pageSheet"
      >
        <View style={{ flex: 1, backgroundColor: colors.background }}>
          <SheetHeader title={text.title} onClose={close} />
          <ScrollView
            contentContainerStyle={{ padding: 20, gap: 16 }}
            keyboardShouldPersistTaps="handled"
          >
            <Text style={style}>{text.hint}</Text>
            <Text style={{ ...style, color: colors.warning }}>{text.limitsUnavailable}</Text>
            <ErrorNotice text={error} />
            {rows.map((row) => (
              <View
                key={row.id}
                style={{
                  gap: 8,
                  borderWidth: 1,
                  borderColor: colors.border,
                  borderRadius: 16,
                  padding: 14,
                }}
              >
                <Text style={style}>
                  {text[authorityStatus(row)]} · {accountName(row.account_id)}
                  {"\n"}
                  {row.envelope.symbols.join(", ")}
                  {"\n"}
                  {new Date(row.valid_until).toLocaleString()}
                </Text>
                {authorityStatus(row) === "pending" && (
                  <Button
                    secondary
                    label={text.review}
                    disabled={busy}
                    onPress={() => {
                      setReview(row);
                      setAcknowledged(false);
                      setEnroll(false);
                    }}
                  />
                )}
                {["active", "pending"].includes(authorityStatus(row)) && (
                  <Button
                    secondary
                    label={text.revoke}
                    disabled={busy}
                    onPress={() =>
                      void execute(async () => {
                        await api.post(
                          `/account-authorities/${encodeURIComponent(row.id)}/revoke`,
                          {},
                        );
                      })
                    }
                  />
                )}
              </View>
            ))}
            {review && (
              <View style={{ gap: 12 }}>
                <Text accessibilityRole="header" style={style}>
                  {text.review}
                </Text>
                <Text style={style}>
                  {accountName(review.account_id)} · {review.envelope.symbols.join(", ")}
                  {"\n"}
                  {review.envelope.actions.map((action) => text[action]).join(" · ")}
                </Text>
                {authorityLimitFields.map((field) => (
                  <Text key={field} style={style}>
                    {text[field]}: {String(review.envelope[field])}
                  </Text>
                ))}
                <Text style={style}>
                  {text.manual}: {review.envelope.allow_manual_positions ? "✓" : "—"}
                </Text>
                <SettingsGroup>
                  <SettingsSwitch
                    label={text.acknowledge}
                    value={acknowledged}
                    disabled={busy}
                    onChange={setAcknowledged}
                  />
                </SettingsGroup>
                {!supported && <Text style={style}>{text.unsupported}</Text>}
                <Button
                  label={text.review}
                  disabled={
                    busy || !supported || !acknowledged || authorityStatus(review) !== "pending"
                  }
                  onPress={() =>
                    void execute(async () => {
                      const updated = await activateAccountAuthority(api, review, deviceProof);
                      if (alive.current && current.current === scope) {
                        setRows((value) =>
                          value.map((row) => (row.id === updated.id ? updated : row)),
                        );
                        setReview(null);
                      }
                    })
                  }
                />
                {enroll && (
                  <>
                    <Field
                      label={text.password}
                      secureTextEntry
                      autoComplete="current-password"
                      value={password}
                      onChangeText={setPassword}
                    />
                    <Button
                      label={text.register}
                      disabled={busy || !password || !supported}
                      onPress={() =>
                        void execute(async () => {
                          const secret = password;
                          setPassword("");
                          const challenge = await api.post<DeviceChallenge>(
                            "/auth/devices/enrollment",
                            { password: secret, name: text.device },
                          );
                          await api.post(
                            "/auth/devices/enrollment/verify",
                            await deviceProof(challenge, true),
                          );
                          if (alive.current && current.current === scope) setEnroll(false);
                        })
                      }
                    />
                  </>
                )}
                <Button
                  secondary
                  label={text.close}
                  disabled={busy}
                  onPress={() => {
                    setReview(null);
                    setPassword("");
                    setEnroll(false);
                  }}
                />
              </View>
            )}
            <Button
              secondary
              label={text.create}
              disabled={busy}
              onPress={() => setCreating((value) => !value)}
            />
            {creating && (
              <View style={{ gap: 14 }}>
                {!threads.length && <Text style={style}>{text.noThread}</Text>}
                {threads.length > 1 && (
                  <SettingsGroup title={text.thread}>
                    {threads.map((thread) => (
                      <SettingsRow
                        key={thread.id}
                        title={thread.title || text.thread}
                        value={thread.id === threadId ? "✓" : ""}
                        onPress={() => setThreadId(thread.id)}
                        disabled={busy}
                      />
                    ))}
                  </SettingsGroup>
                )}
                {agent.trading_symbol ? (
                  <Text style={style}>
                    {accountName(pair.trading_account_id)} · {agent.trading_symbol}
                  </Text>
                ) : (
                  <>
                    <BrokerPairPicker
                      value={pair}
                      onChange={(next) => {
                        if (next.trading_account_id !== pair.trading_account_id) setSymbols([]);
                        setPair(next);
                      }}
                    />
                    <Button
                      secondary
                      label={text.add}
                      disabled={
                        busy ||
                        !pair.trading_symbol ||
                        symbols.includes(pair.trading_symbol) ||
                        symbols.length >= 100
                      }
                      onPress={() => setSymbols((value) => [...value, pair.trading_symbol])}
                    />
                    <View style={{ gap: 6 }}>
                      {symbols.map((symbol) => (
                        <Button
                          key={symbol}
                          secondary
                          label={`${symbol} ×`}
                          disabled={busy}
                          onPress={() =>
                            setSymbols((value) => value.filter((item) => item !== symbol))
                          }
                        />
                      ))}
                    </View>
                  </>
                )}
                <SettingsGroup title={text.actions}>
                  {authorityActions.map((action) => (
                    <SettingsSwitch
                      key={action}
                      label={text[action]}
                      value={actions.includes(action)}
                      disabled={busy}
                      onChange={(enabled) =>
                        setActions((value) =>
                          enabled ? [...value, action] : value.filter((item) => item !== action),
                        )
                      }
                    />
                  ))}
                </SettingsGroup>
                {authorityLimitFields.map((field) => (
                  <Field
                    key={field}
                    label={text[field]}
                    value={draft[field]}
                    editable={!busy}
                    autoCapitalize="none"
                    keyboardType={field === "valid_until" ? "default" : "decimal-pad"}
                    onChangeText={(value) =>
                      setDraft((current) => ({ ...current, [field]: value }))
                    }
                  />
                ))}
                <SettingsGroup>
                  <SettingsSwitch
                    label={text.manual}
                    value={manual}
                    disabled={busy}
                    onChange={setManual}
                  />
                </SettingsGroup>
                <Button
                  label={text.save}
                  disabled={busy || !proposal || agent.execution_mode === "shadow" || agent.paused}
                  onPress={() =>
                    void execute(async () => {
                      if (!proposal) return;
                      const row = await api.post<AccountAuthority>(
                        `/agents/${encodeURIComponent(agent.id)}/account-authorities`,
                        proposal,
                      );
                      if (alive.current && current.current === scope) {
                        setReview(row);
                        setAcknowledged(false);
                        setRows((value) => [
                          row,
                          ...value.filter((existing) => existing.id !== row.id),
                        ]);
                      }
                    })
                  }
                />
              </View>
            )}
          </ScrollView>
        </View>
      </Modal>
    </>
  );
}
