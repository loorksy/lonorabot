import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";
import { ChartSheetProvider } from "../components/chart-sheet";
import { IncomingCallOverlay } from "../components/incoming-call";
import { SheetProvider } from "../components/shell/sheets";
import { ToastProvider } from "../components/shell/toast";
import { colors } from "../components/ui";
import { VoiceOverlay } from "../components/voice-overlay";
import { ListsProvider } from "../lib/lists-state";
import { useOtaUpdates } from "../lib/ota";
import { SessionProvider } from "../lib/session";
import { ShellDataProvider } from "../lib/shell-data";
import { ThemeProvider, useTheme } from "../lib/theme";
import { VoiceSessionProvider } from "../lib/voice-session";

function ThemedStatusBar() {
  const { mode } = useTheme();
  return <StatusBar style={mode === "dark" ? "light" : "dark"} />;
}

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
                      <ThemedStatusBar />
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
