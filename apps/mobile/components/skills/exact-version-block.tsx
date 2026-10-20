import type { SkillVersionControls } from "@lonora/contracts";
import { useEffect, useRef, useState } from "react";
import { Text, View } from "react-native";
import { api, SessionRequestCancelled } from "../../lib/api";
import { useSession } from "../../lib/session";
import { Button, ErrorNotice, Field } from "../ui";
import { semanticVersion, styles } from "./shared";

export function ExactVersionBlock({
  agentId,
  controls,
  onChanged,
}: {
  agentId: string;
  controls: SkillVersionControls;
  onChanged: () => void;
}) {
  const { t, rtl, errorText } = useSession();
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  const [version, setVersion] = useState("");
  const [review, setReview] = useState<{ id: string; version: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  const textAlign = rtl ? "right" : "left";
  const valid =
    /^[a-z0-9][a-z0-9_-]{0,79}$/.test(id) && semanticVersion.test(version) && version.length <= 64;
  const alreadyBlocked =
    !!review &&
    controls.revoked.some((row) => row.skill_id === review.id && row.version === review.version);
  const block = async () => {
    if (!review || alreadyBlocked || busy) return;
    const current = generation.current;
    setBusy(true);
    setError(undefined);
    try {
      await api.post<SkillVersionControls>(
        `/agents/${encodeURIComponent(agentId)}/skills/revocations`,
        {
          skill_id: review.id,
          version: review.version,
          expected_revision: controls.revision,
          reason: "owner_revoked",
        },
      );
      if (current !== generation.current) return;
      setReview(null);
      setOpen(false);
      setId("");
      setVersion("");
      onChanged();
    } catch (cause) {
      if (current === generation.current && !(cause instanceof SessionRequestCancelled)) {
        setError(cause);
        onChanged();
      }
    } finally {
      if (current === generation.current) setBusy(false);
    }
  };
  if (!open)
    return <Button label={t("skillsBlockOther")} secondary onPress={() => setOpen(true)} />;
  return (
    <View style={styles.card} testID="skill-exact-version-block">
      <Text accessibilityRole="header" style={[styles.heading, { textAlign }]}>
        {t(review ? "skillsBlockConfirm" : "skillsBlockOther")}
      </Text>
      <ErrorNotice text={error ? errorText(error) : null} />
      {review ? (
        <>
          <Text style={styles.technical}>
            {review.id} · {review.version}
          </Text>
          <Text style={[styles.hint, { textAlign }]}>{t("skillsBlockWarning")}</Text>
          {alreadyBlocked ? (
            <Text style={[styles.hint, { textAlign }]}>{t("skillsAlreadyBlocked")}</Text>
          ) : null}
          <Button
            label={t("skillsBlockVersion")}
            disabled={busy || alreadyBlocked}
            onPress={() => void block()}
          />
        </>
      ) : (
        <>
          <Field
            label={t("skillsIdentifier")}
            value={id}
            onChangeText={setId}
            maxLength={80}
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.technical}
          />
          <Field
            label={t("skillsVersion")}
            value={version}
            onChangeText={setVersion}
            maxLength={64}
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.technical}
          />
          <Button
            label={t("skillsBlockVersion")}
            disabled={!valid}
            onPress={() => setReview({ id, version })}
          />
        </>
      )}
      <Button
        label={t("cancelAction")}
        disabled={busy}
        secondary
        onPress={() => {
          setOpen(false);
          setReview(null);
          setError(undefined);
        }}
      />
    </View>
  );
}
