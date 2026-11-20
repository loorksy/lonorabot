import { Redirect, useRouter } from "expo-router";
import { ScrollView } from "react-native";
import { IncomingCallSettings } from "../../components/incoming-call-settings";
import { SettingsGroup, SettingsRow } from "../../components/settings-group";
import { SheetHeader } from "../../components/sheet-header";
import { Loading, Screen } from "../../components/ui";
import { useSession } from "../../lib/session";

export default function NotifySettings() {
  const router = useRouter();
  const { ready, owner, t } = useSession();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <SheetHeader title={t("notificationsAndContact")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
        <IncomingCallSettings />
        <SettingsGroup>
          <SettingsRow title={t("voice")} icon="activity" onPress={() => router.push("/voice")} />
        </SettingsGroup>
      </ScrollView>
    </Screen>
  );
}
