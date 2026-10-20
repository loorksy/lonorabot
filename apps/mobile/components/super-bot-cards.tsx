import type { DeviceChallenge, SuperBotRequest } from "@lonora/contracts";
import { mergeSuperBotRequest } from "@lonora/core";
import { useEffect, useRef, useState } from "react";
import {
  AppState,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { ApiError, api, SessionRequestCancelled } from "../lib/api";
import { deviceProof, deviceSupported } from "../lib/device-proof";
import { useSession } from "../lib/session";
import { NativeSymbol } from "./native-symbol";
import { Button, colors, ErrorNotice, Field } from "./ui";

/** Current server projection only: reading this list does not authorize an Agent. */
export function useSuperBotRequests(
  agentId: string | undefined,
  threadId: string,
  revision: number,
) {
  const { owner, server, errorText } = useSession();
  const ownerId = owner?.id;
  const scope = JSON.stringify([server, ownerId, agentId, threadId]);
  const reportError = useRef(errorText);
  reportError.current = errorText;
  const [state, setState] = useState<{
    scope: string;
    rows: SuperBotRequest[];
    error: string | null;
  }>({ scope, rows: [], error: null });
  useEffect(() => {
    void revision;
    if (!agentId || !ownerId) return;
    let active = true;
    void api
      .get<SuperBotRequest[]>(`/agents/${encodeURIComponent(agentId)}/super-bot`)
      .then((rows) => {
        if (active)
          setState((current) => ({
            scope,
            rows: rows
              .filter((row) => row.agent_id === agentId && row.thread_id === threadId)
              .map((row) =>
                mergeSuperBotRequest(
                  (current.scope === scope
                    ? current.rows.find((item) => item.id === row.id)
                    : undefined) ?? row,
                  row,
                ),
              ),
            error: null,
          }));
      })
      .catch((cause) => {
        if (active && !(cause instanceof SessionRequestCancelled))
          setState((current) => ({
            scope,
            rows: current.scope === scope ? current.rows : [],
            error: reportError.current(cause),
          }));
      });
    return () => {
      active = false;
    };
  }, [agentId, ownerId, threadId, revision, scope]);
  return {
    rows: state.scope === scope ? state.rows : [],
    error: state.scope === scope ? state.error : null,
    update: (row: SuperBotRequest) => {
      if (row.agent_id !== agentId || row.thread_id !== threadId) return;
      setState((current) => ({
        scope,
        rows:
          current.scope === scope
            ? current.rows.map((existing) =>
                existing.id === row.id ? mergeSuperBotRequest(existing, row) : existing,
              )
            : [],
        error: null,
      }));
    },
  };
}

export function SuperBotCards({
  agentId,
  threadId,
  revision,
}: {
  agentId: string;
  threadId: string;
  revision: number;
}) {
  const { rows, error, update } = useSuperBotRequests(agentId, threadId, revision);
  if (!rows.length && !error) return null;
  return (
    <View style={{ padding: 12, gap: 12 }}>
      <ErrorNotice text={error} />
      {rows.map((row) => (
        <SuperBotCard key={row.id} row={row} onChange={update} />
      ))}
    </View>
  );
}

/** A chat-sized decision with the signed plan available in its details sheet. */
export function SuperBotCard({
  row,
  onChange,
}: {
  row: SuperBotRequest;
  onChange: (value: SuperBotRequest) => void;
}) {
  const { t, errorText, owner, server, rtl } = useSession();
  const [supported, setSupported] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [enroll, setEnroll] = useState(false);
  const [details, setDetails] = useState(false);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const reportError = useRef(errorText);
  reportError.current = errorText;
  useEffect(() => {
    // Native/domain support must be rechecked after an account or server switch.
    void owner?.id;
    void server;
    alive.current = true;
    let active = true;
    setSupported(null);
    let checking = false;
    const check = async () => {
      if (checking || !active) return;
      checking = true;
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
      } catch (cause) {
        if (active && !(cause instanceof SessionRequestCancelled)) setSupported(false);
      } finally {
        checking = false;
      }
    };
    void check();
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void check();
    });
    return () => {
      active = false;
      alive.current = false;
      subscription.remove();
    };
  }, [owner?.id, server]);
  const statuses = {
    pending: t("devicePending"),
    activated: t("active"),
    expired: t("expired"),
    rejected: t("rejected"),
    cancelled: t("cancelled"),
    paused: t("paused"),
    disabled: t("stopped"),
  };
  useEffect(() => {
    setError(null);
    if (row.status !== "pending") {
      setEnroll(false);
      setPassword("");
    }
  }, [row.status]);
  const text = { textAlign: rtl ? ("right" as const) : ("left" as const) };
  function close() {
    setDetails(false);
    setEnroll(false);
    setPassword("");
  }
  async function act(action: "activate" | "reject" | "stop") {
    if (pending.current) return;
    if (action === "activate" && !supported) {
      setDetails(true);
      setError(t("device_not_supported"));
      return;
    }
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      let result: SuperBotRequest;
      if (action === "activate") {
        const challenge = await api.post<DeviceChallenge>(`/super-bot/${row.id}/challenge`, {});
        result = await api.post<SuperBotRequest>("/super-bot/verify", await deviceProof(challenge));
      } else {
        result = await api.post<SuperBotRequest>("/super-bot/control", {
          request_id: row.id,
          action,
        });
      }
      if (alive.current) {
        onChange(result);
        close();
      }
    } catch (cause) {
      if (alive.current && !(cause instanceof SessionRequestCancelled)) {
        setError(reportError.current(cause));
        if (cause instanceof ApiError && cause.code === "device_registration_required") {
          setDetails(true);
          setEnroll(true);
        }
      }
    } finally {
      pending.current = false;
      if (alive.current) setBusy(false);
    }
  }
  async function register() {
    if (pending.current || !password) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    const current = password;
    setPassword("");
    try {
      const challenge = await api.post<DeviceChallenge>("/auth/devices/enrollment", {
        password: current,
        name: t("myDevice"),
      });
      await api.post("/auth/devices/enrollment/verify", await deviceProof(challenge, true));
      if (alive.current) setEnroll(false);
    } catch (cause) {
      if (alive.current && !(cause instanceof SessionRequestCancelled))
        setError(reportError.current(cause));
    } finally {
      pending.current = false;
      if (alive.current) setBusy(false);
    }
  }
  const actions = (inDetails = false) =>
    row.status === "pending" ? (
      <View style={[styles.actions, { flexDirection: rtl ? "row-reverse" : "row" }]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("approve")}
          disabled={busy || supported === null}
          onPress={() => void act("activate")}
          style={({ pressed }) => [
            styles.action,
            styles.allow,
            (pressed || busy || supported === null) && styles.dimmed,
          ]}
        >
          <Text style={styles.allowLabel}>{t("approve")}</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("reject")}
          disabled={busy}
          onPress={() => void act("reject")}
          style={({ pressed }) => [styles.action, (pressed || busy) && styles.dimmed]}
        >
          <Text style={styles.actionLabel}>{t("reject")}</Text>
        </Pressable>
      </View>
    ) : inDetails && ["activated", "paused"].includes(row.status) ? (
      <Button label={t("superBotStop")} disabled={busy} onPress={() => void act("stop")} />
    ) : null;
  return (
    <>
      <View testID={`super-bot-card-${row.id}`} style={styles.card}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("reviewPlan")}
          onPress={() => setDetails(true)}
          style={{ gap: 8 }}
        >
          <View style={[styles.heading, { flexDirection: rtl ? "row-reverse" : "row" }]}>
            <Text style={[styles.title, text]}>
              {row.status === "pending" ? t("superBotActivationQuestion") : t("superBot")}
            </Text>
            <NativeSymbol name="chevron" color={colors.secondary} size={18} />
          </View>
          <Text style={[styles.copy, text]}>
            <Text style={{ writingDirection: "ltr" }}>{row.envelope.symbol}</Text>
            {" · "}
            {t(row.mode)}
          </Text>
        </Pressable>
        {row.status !== "pending" && (
          <Text
            accessibilityLiveRegion="polite"
            style={[styles.copy, text, row.status === "activated" && { color: colors.success }]}
          >
            {statuses[row.status]}
          </Text>
        )}
        {row.mode === "autonomous" && (
          <Text style={[styles.copy, text, { fontSize: 14 }]}>
            {t("superBotMaximumVolume")}: {row.envelope.maximum_volume ?? "—"} ·{" "}
            {t("maxTradeActions")}: {row.envelope.max_trade_actions}
          </Text>
        )}
        {row.envelope.allow_manual_positions && (
          <Text style={[styles.copy, text, { fontSize: 14, color: colors.warning }]}>
            {t("manualManagementAllowed")}
          </Text>
        )}
        {actions()}
        {!details && <ErrorNotice text={error} />}
      </View>
      <Modal visible={details} transparent animationType="fade" onRequestClose={close}>
        <View style={styles.backdrop}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("close")}
            onPress={close}
            style={StyleSheet.absoluteFill}
          />
          <View
            testID={`super-bot-details-${row.id}`}
            style={styles.sheet}
            accessibilityViewIsModal
          >
            <View style={[styles.heading, { flexDirection: rtl ? "row-reverse" : "row" }]}>
              <Text accessibilityRole="header" style={[styles.title, text]}>
                {t("reviewPlan")}
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t("close")}
                hitSlop={12}
                onPress={close}
              >
                <NativeSymbol name="close" />
              </Pressable>
            </View>
            <ScrollView keyboardShouldPersistTaps="handled" style={{ flexGrow: 0 }}>
              <View style={{ gap: 14, paddingVertical: 16 }}>
                <Text style={[styles.title, text]}>{row.envelope.goal_title}</Text>
                <Text style={[styles.copy, text]}>{row.envelope.objective}</Text>
                <Text style={[styles.copy, text]}>
                  <Text style={{ writingDirection: "ltr" }}>{row.envelope.symbol}</Text>
                  {" · "}
                  {t(row.mode)} · {statuses[row.status]}
                </Text>
                <Text style={[styles.copy, text]}>{t("superBotDeviceConfirmation")}</Text>
                <View style={styles.plan}>
                  <Text style={[styles.copy, text]}>
                    {t("superBotMaximumVolume")}: {row.envelope.maximum_volume ?? "—"}
                  </Text>
                  <Text style={[styles.copy, text]}>
                    {t("maxTradeActions")}: {row.envelope.max_trade_actions}
                  </Text>
                  <Text style={[styles.copy, text]}>
                    {t(
                      row.envelope.allow_manual_positions
                        ? "manualManagementAllowed"
                        : "manualManagementExcluded",
                    )}
                  </Text>
                  {row.envelope.execution_mode === "shadow" && (
                    <Text style={[styles.copy, text]}>{t("shadowMode")}</Text>
                  )}
                </View>
                {row.envelope.steps.map((step) => (
                  <View key={step.id} style={styles.plan}>
                    <Text style={[styles.copy, text]}>{step.title}</Text>
                    {step.trade && (
                      <>
                        <Text style={[styles.copy, { writingDirection: "ltr" }]}>
                          {[
                            step.trade.action,
                            step.trade.symbol,
                            step.trade.volume,
                            step.trade.price,
                            step.trade.position_id ??
                              step.trade.order_id ??
                              step.trade.target_step_id,
                          ]
                            .filter((value) => value != null)
                            .join(" · ")}
                        </Text>
                        <Text style={[styles.copy, text]}>
                          {t("stopLoss")}: {step.trade.stop_loss ?? "—"} · {t("takeProfit")}:{" "}
                          {step.trade.take_profit ?? "—"}
                        </Text>
                      </>
                    )}
                  </View>
                ))}
                <ErrorNotice text={error} />
                {enroll ? (
                  <View style={{ gap: 12 }}>
                    <Field
                      label={t("confirmAccountPassword")}
                      secureTextEntry
                      autoComplete="current-password"
                      value={password}
                      onChangeText={setPassword}
                    />
                    <Button
                      label={t("registerThisDevice")}
                      disabled={busy || !password || !supported}
                      onPress={() => void register()}
                    />
                    <Button
                      label={t("cancelAction")}
                      secondary
                      disabled={busy}
                      onPress={() => {
                        setEnroll(false);
                        setPassword("");
                        setError(null);
                      }}
                    />
                  </View>
                ) : (
                  <>
                    {supported === false && (
                      <>
                        <Text style={[styles.copy, text]}>{t("device_not_supported")}</Text>
                        {Platform.OS !== "web" && (
                          <Button
                            secondary
                            label={t("authorizeOnWeb")}
                            onPress={() => {
                              void Linking.openURL(
                                `${server}/app/${encodeURIComponent(row.agent_id)}?thread=${encodeURIComponent(row.thread_id)}`,
                              ).catch((cause) => setError(reportError.current(cause)));
                            }}
                          />
                        )}
                      </>
                    )}
                    {actions(true)}
                    {row.status === "pending" && supported && (
                      <Button
                        secondary
                        label={t("deviceRegister")}
                        disabled={busy}
                        onPress={() => {
                          setError(null);
                          setEnroll(true);
                        }}
                      />
                    )}
                  </>
                )}
              </View>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  card: {
    width: "100%",
    maxWidth: 540,
    borderRadius: 20,
    padding: 16,
    gap: 14,
    backgroundColor: colors.muted,
  },
  heading: { alignItems: "center", justifyContent: "space-between", gap: 12 },
  title: { color: colors.foreground, fontSize: 17, fontWeight: "600", flexShrink: 1 },
  copy: { color: colors.secondary, fontSize: 16, lineHeight: 24, flexShrink: 1 },
  actions: { gap: 10 },
  action: {
    flex: 1,
    minWidth: 0,
    minHeight: 46,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: colors.accent,
    alignItems: "center",
    justifyContent: "center",
  },
  allow: { backgroundColor: colors.foreground },
  allowLabel: { color: colors.background, fontSize: 16, fontWeight: "600", textAlign: "center" },
  actionLabel: { color: colors.foreground, fontSize: 16, fontWeight: "600", textAlign: "center" },
  dimmed: { opacity: 0.5 },
  backdrop: {
    flex: 1,
    backgroundColor: colors.overlay,
    justifyContent: "flex-end",
    padding: 12,
  },
  sheet: { maxHeight: "88%", borderRadius: 24, backgroundColor: colors.background, padding: 20 },
  plan: { borderTopWidth: 1, borderColor: colors.border, paddingTop: 12, gap: 8 },
});
