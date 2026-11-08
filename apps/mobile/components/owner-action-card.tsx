import type { DeviceChallenge, OwnerAction, OwnerActionDecision } from "@lonora/contracts";
import {
  type CredentialForm,
  type OwnerActionButton,
  ownerActionCard,
  ownerActionChoices,
  ownerActionText,
  submitCredential,
} from "@lonora/core";
import { useEffect, useRef, useState } from "react";
import { Text, View } from "react-native";
import { api } from "../lib/api";
import { ApiError } from "../lib/api-error";
import { deviceProof, deviceSupported } from "../lib/device-proof";
import { useSession } from "../lib/session";
import { SettingsSwitch } from "./settings-group";
import { Button, colors, ErrorNotice, Field } from "./ui";

/**
 * One owner action card, rendered from the same shared spec as Web: server facts in the
 * owner's language and one tap. A grant card, or raising or removing a money limit, asks
 * for the passkey (registering this device inline the first time); a grant card's
 * switches go with that tap. The owner-session route re-validates.
 */
export function OwnerActionCard({
  row,
  onChange,
}: {
  row: OwnerAction;
  onChange: (value: OwnerAction) => void;
}) {
  const { errorText, rtl, locale } = useSession();
  const text = ownerActionText(locale);
  const spec = ownerActionCard(row, locale);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  const [enroll, setEnroll] = useState(false);
  const [password, setPassword] = useState("");
  const [chosen, setChosen] = useState<Record<string, boolean>>({});
  const [supported, setSupported] = useState<boolean | null>(null);
  // A credential card's form: values stay here until posted to the owner API, then clear.
  const [values, setValues] = useState<Record<string, string>>({});
  const pending = useRef(false);
  const align = { textAlign: rtl ? ("right" as const) : ("left" as const) };
  useEffect(() => {
    if (!spec.passkey) return;
    let active = true;
    void Promise.resolve(deviceSupported()).then((value) => {
      if (active) setSupported(value);
    });
    return () => {
      active = false;
    };
  }, [spec.passkey]);
  async function run(task: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(undefined);
    try {
      await task();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "device_registration_required")
        setEnroll(true);
      setError(errorText(reason));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  const decide = (button: OwnerActionButton) =>
    run(async () => {
      const choices = ownerActionChoices(row, chosen);
      const body: OwnerActionDecision = {
        decision: button.decision,
        ...(button.decision === "confirm" ? choices.decision : {}),
      };
      if (button.tier) body.tier = button.tier;
      if (button.outcome) {
        body.outcome = button.outcome;
        if (note.trim()) body.note = note.trim();
        if (reference.trim()) body.broker_reference = reference.trim();
      }
      if (button.decision === "confirm" && spec.passkey) {
        const challenge = await api.post<DeviceChallenge>(
          `/owner-actions/${row.id}/challenge`,
          choices.challenge,
        );
        body.proof = await deviceProof(challenge);
      }
      onChange(await api.post<OwnerAction>(`/owner-actions/${row.id}/decision`, body));
    });
  const connect = (form: CredentialForm) =>
    run(async () => {
      const sent = {
        ...Object.fromEntries(form.fields.map((field) => [field.key, field.initial])),
        ...values,
      };
      setValues({});
      // The value goes straight to the owner API; the card only learns what was created.
      const connected = await submitCredential(
        (path, body) => api.post<{ id: string }>(path, body),
        form.target,
        sent,
      );
      onChange(
        await api.post<OwnerAction>(`/owner-actions/${row.id}/decision`, {
          decision: "confirm",
          connected,
        } satisfies OwnerActionDecision),
      );
    });
  const register = () =>
    run(async () => {
      const secret = password;
      setPassword("");
      const challenge = await api.post<DeviceChallenge>("/auth/devices/enrollment", {
        password: secret,
        name: text.deviceName,
      });
      await api.post("/auth/devices/enrollment/verify", await deviceProof(challenge, true));
      setEnroll(false);
    });
  const blocked = spec.passkey && supported === false;
  return (
    <View
      testID={`owner-action-${row.id}`}
      accessibilityLabel={spec.title}
      style={{
        borderWidth: 1,
        borderColor: colors.border,
        borderStartWidth: 3,
        borderStartColor: row.status === "pending" ? colors.foreground : colors.border,
        padding: 12,
        gap: 8,
      }}
    >
      <Text style={[{ color: colors.foreground, fontWeight: "600" }, align]}>{spec.title}</Text>
      {spec.lines.map((line) => (
        <Text key={line} style={[{ color: colors.foreground }, align]}>
          {line}
        </Text>
      ))}
      {spec.hint ? <Text style={[{ color: colors.secondary }, align]}>{spec.hint}</Text> : null}
      {spec.options.map((option) => (
        <SettingsSwitch
          key={option.key}
          testID={`owner-action-option-${option.key.split(":")[0]}`}
          label={option.label}
          value={chosen[option.key] ?? option.initial}
          disabled={busy}
          onChange={(value) => setChosen((old) => ({ ...old, [option.key]: value }))}
        />
      ))}
      {spec.notes ? (
        <>
          <Field label={text.note} value={note} maxLength={2000} onChangeText={setNote} />
          <Field
            label={text.brokerReference}
            value={reference}
            maxLength={200}
            onChangeText={setReference}
          />
        </>
      ) : null}
      {spec.credential ? (
        <View testID={`owner-action-form-${spec.credential.target}`} style={{ gap: 8 }}>
          {spec.credential.fields.map((field) => (
            <Field
              key={field.key}
              label={field.label}
              secureTextEntry={field.type === "password"}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType={field.type === "url" ? "url" : "default"}
              value={values[field.key] ?? field.initial}
              editable={!busy}
              style={field.ltr ? { textAlign: "left", writingDirection: "ltr" } : undefined}
              onChangeText={(value) => setValues((old) => ({ ...old, [field.key]: value }))}
            />
          ))}
          <Button
            label={spec.credential.submit}
            disabled={
              busy ||
              spec.credential.fields.some(
                (field) => field.required && !(values[field.key] ?? field.initial).trim(),
              )
            }
            onPress={() => void connect(spec.credential as CredentialForm)}
          />
        </View>
      ) : null}
      {blocked ? (
        <Text style={[{ color: colors.secondary }, align]}>{text.passkeyUnsupported}</Text>
      ) : null}
      {enroll ? (
        <>
          <Field
            label={text.password}
            secureTextEntry
            autoComplete="current-password"
            value={password}
            onChangeText={setPassword}
          />
          <Button
            label={text.registerDevice}
            disabled={busy || !password || blocked}
            onPress={() => void register()}
          />
        </>
      ) : null}
      {spec.buttons.length ? (
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", flexWrap: "wrap", gap: 8 }}>
          {spec.buttons.map((button) => (
            <Button
              key={button.key}
              label={button.label}
              secondary={!button.primary}
              disabled={busy || (button.decision === "confirm" && blocked)}
              onPress={() => void decide(button)}
            />
          ))}
        </View>
      ) : null}
      {spec.outcome ? (
        <Text accessibilityRole="text" style={[{ color: colors.secondary }, align]}>
          {spec.outcome}
        </Text>
      ) : null}
      <ErrorNotice text={error} />
    </View>
  );
}
