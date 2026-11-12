import { useRouter } from "expo-router";
import { useEffect } from "react";
import { AppState, Platform } from "react-native";
import { onPushOpened, onPushTokenChange, syncPushDevice } from "../../lib/push";
import { useSession } from "../../lib/session";

/**
 * The notification permission flow (VISION 11.4): once the owner is signed in on a phone, ask
 * for the permission and register this phone; again whenever the app returns to the
 * foreground, so a token the system rotated or a permission changed in Settings is picked up.
 * Signing out removes the phone on the server.
 */
export function usePushRegistration() {
  const { owner } = useSession();
  useEffect(() => {
    if (!owner || Platform.OS === "web") return;
    const run = () => void syncPushDevice().catch(() => undefined);
    run();
    const foreground = AppState.addEventListener("change", (state) => {
      if (state === "active") run();
    });
    const stopRotation = onPushTokenChange(run);
    return () => {
      foreground.remove();
      stopRotation();
    };
  }, [owner]);
}

/** A tapped push opens its conversation at the card (VISION 11.4). */
export function usePushOpen() {
  const { owner } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!owner || Platform.OS === "web") return;
    return onPushOpened(({ threadId, around }) =>
      router.push({
        pathname: "/thread",
        params: around ? { id: threadId, around: String(around) } : { id: threadId },
      }),
    );
  }, [owner, router]);
}

export function PushRegistration() {
  usePushRegistration();
  usePushOpen();
  return null;
}
