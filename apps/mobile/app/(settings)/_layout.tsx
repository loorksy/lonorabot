import { Stack } from "expo-router";
import { colors } from "../../components/ui";
export default function SettingsLayout() {
  return (
    <Stack
      screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }}
    />
  );
}
