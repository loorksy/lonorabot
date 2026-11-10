import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";
import { ChartSheetProvider } from "../components/chart-sheet";
import { IncomingCallOverlay } from "../components/incoming-call";
import { SheetProvider } from "../components/shell/sheets";
import { ToastProvider } from "../components/shell/toast";
import { colors } from "../components/ui";
import { VoiceOverlay } from "../components/voice-overlay";
import { useOtaUpdates } from "../lib/ota";
import { ListsProvider } from "../lib/lists-state";
import { SessionProvider } from "../lib/session";
import { ShellDataProvider } from "../lib/shell-data";
import { ThemeProvider } from "../lib/theme";
import { VoiceSessionProvider } from "../lib/voice-session";

export default function Layout() {
  useOtaUpdates();
  return (
    <SessionProvider>
      <ThemeProvider>
        <ShellDataProvider>
          <ToastProvider>
            <ListsProvider>
              <SheetProvider>
                <VoiceSessionProvider>
                  <ChartSheetProvider>
          <View style={{ flex: 1 }}>
            <StatusBar style="light" />
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: colors.background },
                animation: "slide_from_right",
              }}
            >
              <Stack.Screen name="(tabs)" />
              <Stack.Screen name="sign-in" />
              <Stack.Screen name="agents" />
              <Stack.Screen name="archived" />
              <Stack.Screen name="thread" />
              <Stack.Screen name="new" />
              <Stack.Screen name="charts" />
              <Stack.Screen name="new-group" options={{ presentation: "modal" }} />
              <Stack.Screen name="(settings)" />
              <Stack.Screen name="bot-settings" options={{ presentation: "modal" }} />
              <Stack.Screen name="group-settings" options={{ presentation: "modal" }} />
            </Stack>
            <VoiceOverlay />
            <IncomingCallOverlay />
          </View>
                  </ChartSheetProvider>
                </VoiceSessionProvider>
              </SheetProvider>
            </ListsProvider>
          </ToastProvider>
        </ShellDataProvider>
      </ThemeProvider>
    </SessionProvider>
  );
}
