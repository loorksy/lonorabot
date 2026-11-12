import type { DeviceChallenge } from "@lonora/contracts";
import {
  type OwnerProfileLabel,
  ownerActionText,
  ownerProfileLabel,
  type ReplyLanguage,
  reachMeChannels,
  reachMeHint,
  reachMeLabel,
  replyLanguageLabel,
  replyLanguages,
} from "@lonora/core";
import { useCallback, useEffect, useState } from "react";
import { Switch, Text, View } from "react-native";
import { api } from "../lib/api";
import { deviceProof, deviceSupported } from "../lib/device-proof";
import { type IncomingPolicy, reachMePayload } from "../lib/incoming-call";
import { useSession } from "../lib/session";
import { Button, colors, ErrorNotice, Field } from "./ui";

type OwnerProfile = {
  reply_language: "ar" | "en" | null;
  reach_me: IncomingPolicy;
  devices: { id: string; name: string }[];
};

const row = {
  flexDirection: "row",
  justifyContent: "space-between",
  alignItems: "center",
} as const;

/** How agents reach the owner: the same preference as the web, also set from chat. */
export function IncomingCallSettings() {
  const { locale, errorText } = useSession();
  const label = (key: OwnerProfileLabel) => ownerProfileLabel(key, locale);
  const text = ownerActionText(locale);
  const [policy, setPolicy] = useState<IncomingPolicy | null>(null);
  const [devices, setDevices] = useState<{ id: string; name: string }[]>([]);
  const [language, setLanguage] = useState<ReplyLanguage>("auto");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [password, setPassword] = useState("");
  const [supported, setSupported] = useState<boolean | null>(null);
  const [registered, setRegistered] = useState(false);
  const apply = useCallback((value: OwnerProfile) => {
    setPolicy(value.reach_me);
    setDevices(value.devices);
    setLanguage(value.reply_language ?? "auto");
    setStart(value.reach_me.quiet_start_hour?.toString() ?? "");
    setEnd(value.reach_me.quiet_end_hour?.toString() ?? "");
  }, []);
  useEffect(() => {
    let disposed = false;
    void api
      .get<OwnerProfile>("/owner/profile")
      .then((value) => {
        if (!disposed) apply(value);
      })
      .catch((cause) => {
        if (!disposed) setError(errorText(cause));
      });
    return () => {
      disposed = true;
    };
  }, [errorText, apply]);
  useEffect(() => {
    let disposed = false;
    void Promise.resolve(deviceSupported()).then((value) => {
      if (!disposed) setSupported(value);
    });
    return () => {
      disposed = true;
    };
  }, []);
  // A call rings only a device registered with the owner's passkey (the account password first).
  const register = async () => {
    setSaving(true);
    setError(null);
    setRegistered(false);
    const secret = password;
    setPassword("");
    try {
      const challenge = await api.post<DeviceChallenge>("/auth/devices/enrollment", {
        password: secret,
        name: text.deviceName,
      });
      await api.post("/auth/devices/enrollment/verify", await deviceProof(challenge, true));
      // Only the device list is refreshed: unsaved choices on this screen stay.
      setDevices((await api.get<OwnerProfile>("/owner/profile")).devices);
      setRegistered(true);
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setSaving(false);
    }
  };
  const save = async () => {
    if (!policy) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      apply(
        await api.put<OwnerProfile>("/owner/preferences", {
          reply_language: language === "auto" ? null : language,
          reach_me: reachMePayload(
            policy,
            devices,
            { start, end },
            Intl.DateTimeFormat().resolvedOptions().timeZone,
          ),
        }),
      );
      setSaved(true);
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setSaving(false);
    }
  };
  return (
    <View style={{ gap: 12 }}>
      <Text style={{ color: colors.foreground, fontWeight: "600" }}>{label("reachMe")}</Text>
      <Text style={{ color: colors.secondary, lineHeight: 22 }}>{label("inAppOnly")}</Text>
      <ErrorNotice text={error} />
      {policy ? (
        <>
          {reachMeChannels.map((channel) => (
            <View key={channel} style={{ gap: 4 }}>
              <Button
                label={`${policy.channel === channel ? "✓ " : ""}${reachMeLabel(channel, locale)}`}
                secondary={policy.channel !== channel}
                disabled={saving || (channel === "call" && devices.length === 0)}
                onPress={() => {
                  setSaved(false);
                  // Choosing calls means being called when a decision is needed.
                  setPolicy({
                    ...policy,
                    channel,
                    action_required: channel === "call" ? true : policy.action_required,
                  });
                }}
              />
              <Text style={{ color: colors.secondary }}>{reachMeHint(channel, locale)}</Text>
            </View>
          ))}
          {devices.length === 0 ? (
            <Text style={{ color: colors.secondary }}>{label("noDevice")}</Text>
          ) : null}
          <Field
            label={text.password}
            secureTextEntry
            autoComplete="current-password"
            value={password}
            onChangeText={setPassword}
            editable={!saving && supported !== false}
          />
          {supported === false ? (
            <Text style={{ color: colors.secondary }}>{text.passkeyUnsupported}</Text>
          ) : null}
          {registered ? (
            <Text
              accessibilityLiveRegion="polite"
              accessibilityRole="alert"
              style={{ color: colors.secondary }}
            >
              {label("deviceRegistered")}
            </Text>
          ) : null}
          <Button
            label={label("registerThisDevice")}
            secondary
            disabled={saving || !password || supported !== true}
            onPress={() => void register()}
          />
          {policy.channel === "call" && devices.length > 0 ? (
            <>
              <Text style={{ color: colors.secondary }}>{label("device")}</Text>
              {devices.map((device) => (
                <Button
                  key={device.id}
                  label={`${policy.device_id === device.id ? "✓ " : ""}${device.name}`}
                  secondary
                  onPress={() => setPolicy({ ...policy, device_id: device.id })}
                />
              ))}
              <View style={row}>
                <Text style={{ color: colors.foreground }}>{label("actionRequiredCalls")}</Text>
                <Switch
                  accessibilityLabel={label("actionRequiredCalls")}
                  value={policy.action_required}
                  onValueChange={(value) => setPolicy({ ...policy, action_required: value })}
                />
              </View>
              <View style={row}>
                <Text style={{ color: colors.foreground }}>{label("opportunityCalls")}</Text>
                <Switch
                  accessibilityLabel={label("opportunityCalls")}
                  value={policy.opportunities}
                  onValueChange={(value) => setPolicy({ ...policy, opportunities: value })}
                />
              </View>
            </>
          ) : null}
          <Text style={{ color: colors.secondary }}>{label("quietHours")}</Text>
          <Field
            label={label("quietStart")}
            value={start}
            onChangeText={setStart}
            keyboardType="number-pad"
          />
          <Field
            label={label("quietEnd")}
            value={end}
            onChangeText={setEnd}
            keyboardType="number-pad"
          />
          <Text style={{ color: colors.secondary }}>{label("replyLanguage")}</Text>
          {replyLanguages.map((value) => (
            <Button
              key={value}
              label={`${language === value ? "✓ " : ""}${replyLanguageLabel(value, locale)}`}
              secondary={language !== value}
              onPress={() => {
                setSaved(false);
                setLanguage(value);
              }}
            />
          ))}
          {saved ? <Text style={{ color: colors.secondary }}>{label("saved")}</Text> : null}
          <Button label={label("save")} disabled={saving} onPress={() => void save()} />
        </>
      ) : null}
    </View>
  );
}
