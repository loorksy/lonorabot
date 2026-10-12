import { Redirect, useRouter } from "expo-router";
import { ScrollView, Text } from "react-native";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, Loading, Screen } from "../components/ui";
import { useSession } from "../lib/session";
export default function Settings() {
  const { ready, owner, t } = useSession();
  const router = useRouter();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <SheetHeader title={t("settings")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
        <Button label={t("account")} secondary onPress={() => router.push("/account")} />
        <Button label={t("models")} secondary onPress={() => router.push("/models")} />
        <Button label={t("integrations")} secondary onPress={() => router.push("/integrations")} />
        <Button label={t("voice")} secondary onPress={() => router.push("/voice")} />
        <Button label={t("server")} secondary onPress={() => router.push("/server")} />
        <Text style={{ color: colors.secondary, lineHeight: 24, textAlign: "center" }}>
          {t("threadsPersist")}
        </Text>
      </ScrollView>
    </Screen>
  );
}
