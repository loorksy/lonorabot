import { useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, Text } from "react-native";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, ErrorNotice, Field, Loading, Screen } from "../components/ui";
import { useSession } from "../lib/session";
export default function Server() {
  const { ready, server, t, errorText, changeServer } = useSession();
  const router = useRouter();
  const [value, setValue] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!ready) return <Loading />;
  return (
    <Screen>
      <SheetHeader title={t("server")} />
      <ScrollView
        contentContainerStyle={{ padding: 20, gap: 20 }}
        keyboardShouldPersistTaps="handled"
      >
        <ErrorNotice text={error} />
        <Field
          label={t("server")}
          value={value ?? server}
          onChangeText={setValue}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
        <Text style={{ color: colors.secondary, lineHeight: 24 }}>{t("changeServerHint")}</Text>
        <Button
          label={t("save")}
          disabled={busy || !(value ?? server).trim()}
          onPress={() => {
            setBusy(true);
            void changeServer(value ?? server)
              .then(() => router.replace("/sign-in"))
              .catch((cause) => setError(errorText(cause)))
              .finally(() => setBusy(false));
          }}
        />
      </ScrollView>
    </Screen>
  );
}
