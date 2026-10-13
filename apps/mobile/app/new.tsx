import type { Agent, Thread } from "@lonora/contracts";
import { Redirect, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView } from "react-native";
import { AvatarPicker } from "../components/avatar-picker";
import { SheetHeader } from "../components/sheet-header";
import { Button, ErrorNotice, Field, Loading, Screen } from "../components/ui";
import { api } from "../lib/api";
import { useSession } from "../lib/session";

export default function NewAgent() {
  const { ready, owner, t, errorText } = useSession();
  const router = useRouter();
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState("#8B5CF6");
  const [avatar, setAvatar] = useState("orb");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const agent = await api.post<Agent>("/agents", {
        name: name.trim(),
        title: title.trim(),
        description: description.trim(),
        avatar,
        color,
      });
      const thread = await api.post<Thread>(
        `/agents/${encodeURIComponent(agent.id)}/conversation`,
        {},
      );
      router.replace({ pathname: "/thread", params: { id: thread.id } });
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen>
      <SheetHeader title={t("newAgent")} onClose={() => router.back()} />
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ padding: 24, gap: 24 }}
      >
        <AvatarPicker
          name={name}
          color={color}
          avatar={avatar}
          onChange={(shape, value) => {
            setAvatar(shape);
            setColor(value);
          }}
        />
        <Field label={t("name")} value={name} onChangeText={setName} maxLength={80} autoFocus />
        <Field label={t("title")} value={title} onChangeText={setTitle} maxLength={160} />
        <Field
          label={t("description")}
          value={description}
          onChangeText={setDescription}
          maxLength={2000}
          multiline
          style={{ minHeight: 108, textAlignVertical: "top" }}
        />
        <ErrorNotice text={error} />
        <Button
          label={busy ? t("connecting") : t("create")}
          onPress={() => void create()}
          disabled={busy || !name.trim()}
        />
      </ScrollView>
    </Screen>
  );
}
