import type {
  AgentSkill,
  Resource,
  SkillCatalogDetail,
  SkillCatalogEntry,
  SkillRevocationReason,
  SkillVersionControls,
} from "@lonora/contracts";
import { useEffect, useRef, useState } from "react";
import { Modal, Pressable, ScrollView, Text, View } from "react-native";
import { ApiError, api, SessionRequestCancelled } from "../../lib/api";
import { useSession } from "../../lib/session";
import { SettingsGroup, SettingsSwitch } from "../settings-group";
import { SheetHeader } from "../sheet-header";
import { Button, colors, ErrorNotice, Field, Loading, Screen } from "../ui";
import { reasons, semanticVersion, styles } from "./shared";

export function SkillDetails({
  agentId,
  entry,
  controls,
  onClose,
  onChanged,
}: {
  agentId: string;
  entry: SkillCatalogEntry;
  controls: SkillVersionControls;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t, rtl, errorText } = useSession();
  const [detail, setDetail] = useState<SkillCatalogDetail | null>(null);
  const [resource, setResource] = useState<Resource<AgentSkill> | null>(null);
  const [content, setContent] = useState("");
  const [version, setVersion] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<{ id: string; version: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [reason, setReason] = useState<SkillRevocationReason>("owner_revoked");
  const [saved, setSaved] = useState(false);
  const generation = useRef(0);
  const prefix = `/agents/${encodeURIComponent(agentId)}/skills`;
  const textAlign = rtl ? "right" : "left";
  useEffect(() => {
    const current = ++generation.current;
    void Promise.all([
      api.get<SkillCatalogDetail>(`${prefix}/catalog/${encodeURIComponent(entry.id)}`),
      entry.resource_id
        ? api.get<Resource<AgentSkill>>(`/skills/${encodeURIComponent(entry.resource_id)}`)
        : Promise.resolve(null),
    ])
      .then(([value, installed]) => {
        if (current !== generation.current) return;
        if (installed && installed.agent_id !== agentId) return;
        setDetail(value);
        setResource(installed);
        setContent(installed?.payload.content ?? value.content);
        setVersion(installed?.payload.manifest?.version ?? value.version ?? "");
        setEnabled(installed?.payload.enabled !== false);
      })
      .catch((cause) => {
        if (current === generation.current && !(cause instanceof SessionRequestCancelled))
          setError(cause);
      });
    return () => {
      generation.current++;
    };
  }, [prefix, entry.id, entry.resource_id, agentId]);
  const exactVersion = detail?.version ?? entry.version;
  const blocked = controls.revoked.some(
    (row) => row.skill_id === entry.id && row.version === exactVersion,
  );
  const editable = !!resource && entry.source !== "builtin" && !entry.id.endsWith("@installed");
  const save = async () => {
    if (!resource || !editable || busy) return;
    if (resource.payload.manifest && (!semanticVersion.test(version) || version.length > 64))
      return;
    const current = generation.current;
    setBusy(true);
    setError(undefined);
    setSaved(false);
    try {
      const payload: AgentSkill = {
        ...resource.payload,
        content,
        enabled,
        manifest: resource.payload.manifest ? { ...resource.payload.manifest, version } : null,
      };
      const updated = await api.put<Resource<AgentSkill>>(
        `/skills/${encodeURIComponent(resource.id)}`,
        { payload, version: resource.version },
      );
      if (current !== generation.current) return;
      setResource(updated);
      setDetail((currentDetail) =>
        currentDetail
          ? {
              ...currentDetail,
              version: updated.payload.manifest?.version ?? currentDetail.version,
              manifest: updated.payload.manifest ?? currentDetail.manifest,
              content: updated.payload.content,
              resource_version: updated.version,
            }
          : currentDetail,
      );
      setSaved(true);
      onChanged();
    } catch (cause) {
      if (current === generation.current && !(cause instanceof SessionRequestCancelled))
        setError(cause);
    } finally {
      if (current === generation.current) setBusy(false);
    }
  };
  const revoke = async () => {
    const target = confirm;
    if (
      !target ||
      busy ||
      controls.revoked.some((row) => row.skill_id === target.id && row.version === target.version)
    )
      return;
    const current = generation.current;
    setBusy(true);
    setError(undefined);
    try {
      await api.post<SkillVersionControls>(`${prefix}/revocations`, {
        skill_id: target.id,
        version: target.version,
        expected_revision: controls.revision,
        reason,
      });
      if (current !== generation.current) return;
      onChanged();
      onClose();
    } catch (cause) {
      if (current === generation.current && !(cause instanceof SessionRequestCancelled)) {
        setError(cause);
        // Refresh the optimistic revision; never automatically repeat the denial.
        onChanged();
      }
    } finally {
      if (current === generation.current) setBusy(false);
    }
  };
  const remove = async () => {
    if (!resource || entry.source === "builtin" || busy || !confirmDelete) return;
    const current = generation.current;
    setBusy(true);
    setError(undefined);
    try {
      const result = await api.delete<{ deleted: boolean }>(
        `/skills/${encodeURIComponent(resource.id)}`,
      );
      if (current !== generation.current) return;
      if (result.deleted !== true) throw new ApiError("request_failed", 502);
      onChanged();
      onClose();
    } catch (cause) {
      if (current === generation.current && !(cause instanceof SessionRequestCancelled))
        setError(cause);
    } finally {
      if (current === generation.current) setBusy(false);
    }
  };
  return (
    <Modal visible animationType="slide" onRequestClose={() => !busy && onClose()}>
      <Screen>
        <SheetHeader title={t("skillsDetails")} onClose={() => !busy && onClose()} />
        <ScrollView
          contentContainerStyle={styles.page}
          keyboardShouldPersistTaps="handled"
          testID="skill-details"
        >
          <Text accessibilityRole="header" style={[styles.heading, { textAlign }]}>
            {detail?.title ?? entry.title}
          </Text>
          <Text style={styles.technical}>
            {entry.id} · {exactVersion ?? "—"}
          </Text>
          <Text style={[styles.hint, { textAlign }]}>
            {detail?.description ?? entry.description}
          </Text>
          <ErrorNotice text={error ? errorText(error) : null} />
          {!detail && !error ? <Loading /> : null}
          {detail?.manifest ? (
            <SettingsGroup>
              <View style={{ gap: 9 }}>
                <Text style={[styles.hint, { textAlign }]}>
                  {t("skillsActivation")}
                  {": "}
                  {t(
                    detail.manifest.activation.mode === "automatic"
                      ? "skillsAutomatic"
                      : detail.manifest.activation.mode === "explicit"
                        ? "skillsExplicit"
                        : "skillsTriggered",
                  )}
                </Text>
                <Text style={[styles.hint, { textAlign }]}>
                  {t(
                    detail.manifest.risk_class === "read_only"
                      ? "skillsReadOnly"
                      : detail.manifest.risk_class === "state_mutating"
                        ? "skillsStateChange"
                        : detail.manifest.risk_class === "external_action"
                          ? "skillsExternal"
                          : "skillsFinancial",
                  )}
                </Text>
                {detail.manifest.dependencies.length ? (
                  <>
                    <Text style={[styles.hint, { textAlign }]}>{t("skillsDependencies")}</Text>
                    <Text style={styles.technical}>{detail.manifest.dependencies.join(", ")}</Text>
                  </>
                ) : null}
                {detail.manifest.required_tools.length ? (
                  <>
                    <Text style={[styles.hint, { textAlign }]}>{t("skillsTools")}</Text>
                    <Text style={styles.technical}>
                      {detail.manifest.required_tools.join(", ")}
                    </Text>
                  </>
                ) : null}
              </View>
            </SettingsGroup>
          ) : null}
          {editable ? (
            <>
              {resource?.payload.manifest ? (
                <>
                  <Field
                    label={t("skillsVersion")}
                    value={version}
                    onChangeText={(value) => {
                      setVersion(value);
                      setSaved(false);
                    }}
                    maxLength={64}
                    autoCapitalize="none"
                    style={styles.technical}
                  />
                  <Text style={[styles.hint, { textAlign }]}>{t("skillsVersionHint")}</Text>
                </>
              ) : null}
              <Field
                label={t("skillsInstructions")}
                value={content}
                onChangeText={(value) => {
                  setContent(value);
                  setSaved(false);
                }}
                maxLength={16000}
                editable={!busy}
                multiline
                style={{ minHeight: 190, textAlignVertical: "top" }}
              />
              <SettingsGroup>
                <SettingsSwitch
                  label={t("skillsEnabled")}
                  disabled={busy}
                  value={enabled}
                  onChange={(value) => {
                    setEnabled(value);
                    setSaved(false);
                  }}
                />
              </SettingsGroup>
              {resource?.payload.manifest && !semanticVersion.test(version) ? (
                <Text style={[styles.hint, { color: colors.error, textAlign }]}>
                  {t("skillsVersionInvalid")}
                </Text>
              ) : null}
              <Button
                label={t("save")}
                onPress={() => void save()}
                disabled={
                  busy ||
                  !content.trim() ||
                  (!!resource?.payload.manifest && !semanticVersion.test(version))
                }
              />
              {saved ? (
                <Text style={[styles.hint, { color: colors.success, textAlign }]}>
                  {t("saved")}
                </Text>
              ) : null}
            </>
          ) : detail ? (
            <>
              {entry.source === "builtin" ? (
                <Text style={[styles.hint, { textAlign }]}>{t("skillsBuiltinReadOnly")}</Text>
              ) : null}
              <Text style={[styles.hint, { textAlign }]}>{t("skillsInstructions")}</Text>
              <Text selectable style={[styles.instructions, { textAlign }]}>
                {detail.content}
              </Text>
            </>
          ) : null}
          {confirm ? (
            <View style={styles.card} testID="skill-version-confirmation">
              <Text accessibilityRole="header" style={[styles.heading, { textAlign }]}>
                {t("skillsBlockConfirm")}
              </Text>
              <Text style={styles.technical}>
                {confirm.id} · {confirm.version}
              </Text>
              <Text style={[styles.hint, { textAlign }]}>{t("skillsBlockWarning")}</Text>
              <Text style={[styles.hint, { textAlign }]}>{t("skillsBlockReason")}</Text>
              {reasons.map((option) => (
                <Pressable
                  key={option.id}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: reason === option.id }}
                  onPress={() => setReason(option.id)}
                  disabled={busy}
                  style={[
                    styles.option,
                    reason === option.id && { borderColor: colors.foreground },
                  ]}
                >
                  <Text style={[styles.hint, { color: colors.foreground, textAlign }]}>
                    {t(option.label)}
                    {reason === option.id ? " ✓" : ""}
                  </Text>
                </Pressable>
              ))}
              <Button
                label={t("skillsBlockVersion")}
                disabled={
                  busy ||
                  controls.revoked.some(
                    (row) => row.skill_id === confirm.id && row.version === confirm.version,
                  )
                }
                onPress={() => void revoke()}
              />
              <Button
                label={t("cancelAction")}
                disabled={busy}
                secondary
                onPress={() => setConfirm(null)}
              />
            </View>
          ) : blocked ? (
            <Text style={[styles.hint, { textAlign }]}>{t("skillsAlreadyBlocked")}</Text>
          ) : detail?.version && !entry.id.endsWith("@installed") && !confirmDelete ? (
            <Button
              label={t("skillsBlockVersion")}
              secondary
              disabled={busy}
              onPress={() => {
                if (detail.version) setConfirm({ id: detail.id, version: detail.version });
              }}
            />
          ) : null}
          {resource && entry.source !== "builtin" ? (
            confirmDelete ? (
              <View style={styles.card} testID="skill-delete-confirmation">
                <Text accessibilityRole="header" style={[styles.heading, { textAlign }]}>
                  {t("skillsDeleteConfirm")}
                </Text>
                <Text style={styles.technical}>
                  {entry.id} · {resource.payload.manifest?.version ?? detail?.version ?? "—"}
                </Text>
                <Text style={[styles.hint, { textAlign }]}>{t("skillsDeleteWarning")}</Text>
                <Button
                  label={t("skillsDelete")}
                  secondary
                  disabled={busy}
                  onPress={() => void remove()}
                />
                <Button
                  label={t("cancelAction")}
                  secondary
                  disabled={busy}
                  onPress={() => setConfirmDelete(false)}
                />
              </View>
            ) : (
              <Button
                label={t("skillsDelete")}
                secondary
                disabled={busy}
                onPress={() => {
                  setConfirmDelete(true);
                  setConfirm(null);
                }}
              />
            )
          ) : null}
          <Button label={t("close")} secondary disabled={busy} onPress={onClose} />
        </ScrollView>
      </Screen>
    </Modal>
  );
}
