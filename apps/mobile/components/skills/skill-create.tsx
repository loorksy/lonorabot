import type { AgentSkill, Resource } from "@lonora/contracts";
import { useEffect, useRef, useState } from "react";
import { Text, View } from "react-native";
import { ApiError, api, SessionRequestCancelled } from "../../lib/api";
import { useSession } from "../../lib/session";
import { Button, ErrorNotice, Field } from "../ui";
import { semanticVersion, styles } from "./shared";

export function SkillCreate({ agentId, onChanged }: { agentId: string; onChanged: () => void }) {
  const { t, rtl, errorText } = useSession();
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [content, setContent] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const inflight = useRef(false);
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  const textAlign = rtl ? "right" : "left";
  const valid =
    /^[a-z0-9][a-z0-9_-]{0,79}$/.test(id) &&
    semanticVersion.test(version) &&
    version.length <= 64 &&
    !!title.trim() &&
    !!purpose.trim() &&
    !!content.trim();
  const reset = () => {
    setId("");
    setTitle("");
    setPurpose("");
    setContent("");
    setVersion("1.0.0");
    setError(undefined);
    setOpen(false);
  };
  const create = async () => {
    if (!valid || inflight.current) return;
    const current = generation.current;
    inflight.current = true;
    setBusy(true);
    setError(undefined);
    const payload: AgentSkill = {
      name: id,
      content,
      enabled: true,
      manifest: {
        id,
        version,
        title: title.trim(),
        description: purpose.trim(),
        source: "owner",
        stability: "stable",
        activation: { mode: "explicit", intents: [], triggers: [] },
        risk_class: "read_only",
        required_tools: [],
        required_capabilities: [],
        dependencies: [],
        conflicts: [],
        priority: 50,
        context_budget: 16000,
      },
    };
    try {
      const saved = await api.post<Resource<AgentSkill>>("/skills", { agent_id: agentId, payload });
      if (current !== generation.current) return;
      if (saved.agent_id !== agentId || saved.payload.name !== id)
        throw new ApiError("request_failed", 502);
      reset();
      onChanged();
    } catch (cause) {
      if (current === generation.current && !(cause instanceof SessionRequestCancelled))
        setError(cause);
    } finally {
      inflight.current = false;
      if (current === generation.current) setBusy(false);
    }
  };
  if (!open) return <Button label={t("skillsAdd")} secondary onPress={() => setOpen(true)} />;
  return (
    <View style={styles.card} testID="skill-create">
      <Text accessibilityRole="header" style={[styles.heading, { textAlign }]}>
        {t("skillsAdd")}
      </Text>
      <Text style={[styles.hint, { textAlign }]}>{t("skillsCreateHint")}</Text>
      <ErrorNotice text={error ? errorText(error) : null} />
      <Field
        label={t("skillsIdentifier")}
        value={id}
        onChangeText={setId}
        maxLength={80}
        editable={!busy}
        autoCapitalize="none"
        autoCorrect={false}
        style={styles.technical}
      />
      <Text style={[styles.hint, { textAlign }]}>{t("skillsIdentifierHint")}</Text>
      <Field
        label={t("title")}
        value={title}
        onChangeText={setTitle}
        maxLength={160}
        editable={!busy}
      />
      <Field
        label={t("skillsPurpose")}
        value={purpose}
        onChangeText={setPurpose}
        maxLength={1000}
        editable={!busy}
        multiline
      />
      <Field
        label={t("skillsVersion")}
        value={version}
        onChangeText={setVersion}
        maxLength={64}
        editable={!busy}
        autoCapitalize="none"
        autoCorrect={false}
        style={styles.technical}
      />
      <Field
        label={t("skillsInstructions")}
        value={content}
        onChangeText={setContent}
        maxLength={16000}
        editable={!busy}
        multiline
        style={{ minHeight: 150, textAlignVertical: "top" }}
      />
      <Button label={t("skillsCreate")} onPress={() => void create()} disabled={!valid || busy} />
      <Button label={t("cancelAction")} secondary onPress={reset} disabled={busy} />
    </View>
  );
}
