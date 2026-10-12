import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { colors } from "../components/ui";
import { SessionProvider } from "../lib/session";

export default function Layout() {
  return (
    <SessionProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: colors.background },
          animation: "slide_from_right",
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="sign-in" />
        <Stack.Screen name="thread" />
        <Stack.Screen name="new" options={{ presentation: "modal" }} />
        <Stack.Screen name="new-group" options={{ presentation: "modal" }} />
        <Stack.Screen name="settings" options={{ presentation: "modal" }} />
      </Stack>
    </SessionProvider>
  );
}
