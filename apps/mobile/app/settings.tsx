import { Redirect, useRouter } from "expo-router";
import { ScrollView, Text, View } from "react-native";
import { SettingsGroup, SettingsRow } from "../components/settings-group";
import { SheetHeader } from "../components/sheet-header";
import { colors, Loading, Screen } from "../components/ui";
import { useSession } from "../lib/session";
export default function Settings() {
  const { ready, owner, t } = useSession();
  const router = useRouter();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <SheetHeader title={t("settings")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 24 }}>
        <View style={{ alignItems: "center", gap: 8, paddingVertical: 16 }}>
          <View
            style={{
              width: 64,
              height: 64,
              borderRadius: 32,
              backgroundColor: colors.accent,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Text style={{ color: colors.foreground, fontSize: 23, fontWeight: "600" }}>
              {owner.email.slice(0, 2).toUpperCase()}
            </Text>
          </View>
          <Text
            selectable
            style={{ color: colors.secondary, fontSize: 14, writingDirection: "ltr" }}
          >
            {owner.email}
          </Text>
        </View>
        <SettingsGroup>
          <SettingsRow title={t("account")} icon="agent" onPress={() => router.push("/account")} />
          <SettingsRow title={t("models")} icon="settings" onPress={() => router.push("/models")} />
          <SettingsRow
            title={t("integrations")}
            icon="layers"
            onPress={() => router.push("/integrations")}
          />
          <SettingsRow title={t("voice")} icon="activity" onPress={() => router.push("/voice")} />
        </SettingsGroup>
        <SettingsGroup>
          <SettingsRow title={t("server")} icon="globe" onPress={() => router.push("/server")} />
        </SettingsGroup>
      </ScrollView>
    </Screen>
  );
}
