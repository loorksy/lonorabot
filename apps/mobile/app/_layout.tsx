import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";
import { colors } from "../components/ui";
import { VoiceOverlay } from "../components/voice-overlay";
import { useOtaUpdates } from "../lib/ota";
import { SessionProvider } from "../lib/session";
import { VoiceSessionProvider } from "../lib/voice-session";

export default function Layout() {
  useOtaUpdates();
  return (
    <SessionProvider>
      <VoiceSessionProvider>
        <View style={{ flex: 1 }}>
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
            <Stack.Screen name="charts" />
            <Stack.Screen name="new-group" options={{ presentation: "modal" }} />
            <Stack.Screen name="(settings)" />
            <Stack.Screen name="bot-settings" options={{ presentation: "modal" }} />
            <Stack.Screen name="group-settings" options={{ presentation: "modal" }} />
            <Stack.Screen name="settings" options={{ presentation: "modal" }} />
          </Stack>
          <VoiceOverlay />
        </View>
      </VoiceSessionProvider>
    </SessionProvider>
  );
}
