import { useRouter } from "expo-router";
import { Text, View } from "react-native";
import { Button, colors, Screen } from "../components/ui";
import { useSession } from "../lib/session";

export default function NotFound() {
  const router = useRouter();
  const { t } = useSession();
  return (
    <Screen>
      <View style={{ flex: 1, justifyContent: "center", padding: 32, gap: 24 }}>
        <Text style={{ color: colors.foreground, fontSize: 24, textAlign: "center" }}>
          {t("pageMissing")}
        </Text>
        <Button label={t("inbox")} onPress={() => router.replace("/")} />
      </View>
    </Screen>
  );
}
