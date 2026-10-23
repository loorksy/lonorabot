import type { Agent } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { AppState, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "../lib/api";
import {
  acceptedIncoming,
  type IncomingCall,
  type IncomingPolicy,
  visibleIncoming,
} from "../lib/incoming-call";
import labels from "../lib/incoming-call-labels.json";
import { useSession } from "../lib/session";
import { useVoiceSession } from "../lib/voice-session";
import { Button, colors, ErrorNotice } from "./ui";

/** Foreground invitation surface only; no claim of native background/terminated delivery. */
export function IncomingCallOverlay() {
  const { owner, locale, errorText } = useSession();
  const voice = useVoiceSession();
  const insets = useSafeAreaInsets();
  const [call, setCall] = useState<IncomingCall | null>(null);
  const [device, setDevice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const text = labels[locale];
  useEffect(() => {
    if (!owner) {
      setCall(null);
      return;
    }
    let disposed = false;
    let loading = false;
    const tick = async () => {
      if (loading || AppState.currentState !== "active" || voice.origin) return;
      loading = true;
      try {
        const policy = await api.get<IncomingPolicy>("/voice/incoming/policy");
        if (disposed) return;
        setDevice(policy.device_id);
        if (!policy.enabled) {
          setCall(null);
          return;
        }
        const rows = await api.get<IncomingCall[]>("/voice/incoming");
        if (!disposed) setCall(visibleIncoming(rows));
      } catch {
        /* Session recovery owns transport failures; do not spam ordinary chat. */
      } finally {
        loading = false;
      }
    };
    void tick();
    const timer = setInterval(() => {
      void tick();
    }, 3000);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void tick();
      else setCall(null);
    });
    return () => {
      disposed = true;
      clearInterval(timer);
      subscription.remove();
    };
  }, [owner, voice.origin]);
  if (!call || !device || voice.origin) return null;
  const respond = async (action: "accept" | "reject") => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<IncomingCall>(
        `/voice/incoming/${encodeURIComponent(call.id)}/respond`,
        { action, device_id: device },
      );
      setCall(null);
      if (action === "accept" && acceptedIncoming(result)) {
        const agent = await api.get<Agent>(`/agents/${encodeURIComponent(result.agent_id)}`);
        await voice.start(agent, result.thread_id);
      }
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <View
      accessibilityLiveRegion="polite"
      style={{
        position: "absolute",
        top: insets.top + 12,
        left: 12,
        right: 12,
        zIndex: 110,
        backgroundColor: colors.accent,
        borderRadius: 24,
        borderWidth: 1,
        borderColor: colors.border,
        padding: 18,
        gap: 12,
      }}
    >
      <Text style={{ color: colors.foreground, fontWeight: "600" }}>{text.title}</Text>
      <Text style={{ color: colors.foreground }}>{call.reason}</Text>
      <ErrorNotice text={error} />
      <View style={{ flexDirection: "row", gap: 12 }}>
        <View style={{ flex: 1 }}>
          <Button
            label={text.accept}
            disabled={busy}
            onPress={() => {
              void respond("accept");
            }}
          />
        </View>
        <View style={{ flex: 1 }}>
          <Button
            label={text.reject}
            secondary
            disabled={busy}
            onPress={() => {
              void respond("reject");
            }}
          />
        </View>
      </View>
    </View>
  );
}
