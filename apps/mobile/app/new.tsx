import type { Agent, Thread } from "@lonora/contracts";
import type { AgentMarketMode } from "@lonora/core";
import { Redirect, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView } from "react-native";
import { AgentMarketPicker } from "../components/agent-market-picker";
import { AvatarPicker } from "../components/avatar-picker";
import type { BrokerPair } from "../components/broker-pair-picker";
import { SheetHeader } from "../components/sheet-header";
import { Button, ErrorNotice, Field, Loading, Screen } from "../components/ui";
import { api } from "../lib/api";
import { useSession } from "../lib/session";

export default function NewAgent() {
  const { ready, owner, t, errorText } = useSession();
  const router = useRouter();
  const [pair, setPair] = useState<BrokerPair>({ trading_account_id: "", trading_symbol: "" });
  const [mode, setMode] = useState<AgentMarketMode>("general");
  const [instructions, setInstructions] = useState("");
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
        scope_mode: "flexible",
        trading_account_id: mode === "market" ? pair.trading_account_id : null,
        trading_symbol: mode === "market" ? pair.trading_symbol : null,
        instructions: instructions.trim(),
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
        <Field
          label={t("instructions")}
          value={instructions}
          onChangeText={setInstructions}
          maxLength={16000}
          multiline
        />
        <AgentMarketPicker mode={mode} pair={pair} onMode={setMode} onPair={setPair} />
        <ErrorNotice text={error} />
        <Button
          label={busy ? t("connecting") : t("create")}
          onPress={() => void create()}
          disabled={
            busy ||
            !name.trim() ||
            (mode === "market" && (!pair.trading_account_id || !pair.trading_symbol))
          }
        />
      </ScrollView>
    </Screen>
  );
}
