import { useEffect, useState } from "react";
import { Switch, Text, View } from "react-native";
import { api } from "../lib/api";
import type { IncomingPolicy } from "../lib/incoming-call";
import labels from "../lib/incoming-call-labels.json";
import { useSession } from "../lib/session";
import { Button, colors, ErrorNotice, Field } from "./ui";

export function IncomingCallSettings() {
  const { locale, errorText } = useSession();
  const text = labels[locale];
  const [policy, setPolicy] = useState<IncomingPolicy | null>(null);
  const [devices, setDevices] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  useEffect(() => {
    let disposed = false;
    void Promise.all([
      api.get<IncomingPolicy>("/voice/incoming/policy"),
      api.get<{ id: string; name: string }[]>("/auth/devices"),
    ])
      .then(([value, enrolled]) => {
        if (disposed) return;
        setPolicy(value);
        setDevices(enrolled);
        setStart(value.quiet_start_hour?.toString() ?? "");
        setEnd(value.quiet_end_hour?.toString() ?? "");
      })
      .catch((cause) => {
        if (!disposed) setError(errorText(cause));
      });
    return () => {
      disposed = true;
    };
  }, [errorText]);
  const save = async (next: IncomingPolicy) => {
    setSaving(true);
    setError(null);
    try {
      setPolicy(await api.put<IncomingPolicy>("/voice/incoming/policy", next));
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setSaving(false);
    }
  };
  return (
    <View style={{ gap: 12 }}>
      <Text style={{ color: colors.foreground, fontWeight: "600" }}>{text.settings}</Text>
      <Text style={{ color: colors.secondary, lineHeight: 22 }}>{text.limited}</Text>
      <ErrorNotice text={error} />
      {policy ? (
        <>
          <Text style={{ color: colors.secondary }}>{text.device}</Text>
          {devices.map((device) => (
            <Button
              key={device.id}
              label={`${policy.device_id === device.id ? "✓ " : ""}${device.name}`}
              secondary
              onPress={() => setPolicy({ ...policy, device_id: device.id })}
            />
          ))}
          {devices.length === 0 ? (
            <Text style={{ color: colors.secondary }}>{text.noDevice}</Text>
          ) : null}
          <View
            style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}
          >
            <Text style={{ color: colors.foreground }}>{text.opportunities}</Text>
            <Switch
              accessibilityLabel={text.opportunities}
              value={policy.opportunities}
              onValueChange={(value) => setPolicy({ ...policy, opportunities: value })}
            />
          </View>
          <View
            style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}
          >
            <Text style={{ color: colors.foreground }}>{text.actionRequired}</Text>
            <Switch
              accessibilityLabel={text.actionRequired}
              value={policy.action_required}
              onValueChange={(value) => setPolicy({ ...policy, action_required: value })}
            />
          </View>
          <Field
            label={text.quietStart}
            value={start}
            onChangeText={setStart}
            keyboardType="number-pad"
          />
          <Field
            label={text.quietEnd}
            value={end}
            onChangeText={setEnd}
            keyboardType="number-pad"
          />
          <Button
            label={policy.enabled ? text.disable : text.enable}
            disabled={saving || !policy.device_id}
            onPress={() => {
              void save({
                ...policy,
                enabled: !policy.enabled,
                quiet_start_hour: start.trim() ? Number(start) : null,
                quiet_end_hour: end.trim() ? Number(end) : null,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
              });
            }}
          />
          <Button
            label={text.save}
            secondary
            disabled={saving}
            onPress={() => {
              void save({
                ...policy,
                quiet_start_hour: start.trim() ? Number(start) : null,
                quiet_end_hour: end.trim() ? Number(end) : null,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
              });
            }}
          />
        </>
      ) : null}
    </View>
  );
}
