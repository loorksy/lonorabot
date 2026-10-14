import * as Updates from "expo-updates";
import { useEffect } from "react";
import { AppState, Platform } from "react-native";
import { createUpdateChecker } from "./ota-checker";

export function useOtaUpdates() {
  useEffect(() => {
    if (Platform.OS === "web" || __DEV__ || !Updates.isEnabled) return;
    const checker = createUpdateChecker(
      {
        check: Updates.checkForUpdateAsync,
        fetch: Updates.fetchUpdateAsync,
      },
      { onFailure: () => console.warn("ota_update_check_failed") },
    );
    const listener = AppState.addEventListener("change", (state) => {
      if (state === "active") void checker.check();
    });
    // Native ON_LOAD handles startup; only foreground transitions trigger another check.
    return () => {
      listener.remove();
      checker.stop();
    };
  }, []);
}
