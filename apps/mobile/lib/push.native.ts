import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { ApiError, api } from "./api";
import { loadSetting, saveSetting } from "./storage";

// The owner's own Expo project, built in by the native release (docs/operations.md). A build
// without it has no push: nothing asks for the permission and nothing is registered.
function projectId(): string | null {
  const value = Constants.expoConfig?.extra?.eas?.projectId;
  return typeof value === "string" && value ? value : null;
}

// A random id per install, so the server keeps one row per phone. It names the phone, not
// the owner; the signed-in session is what authorizes the registration.
async function deviceId(): Promise<string> {
  const stored = await loadSetting("lonora.push.device");
  if (stored) return stored;
  const created =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  await saveSetting("lonora.push.device", created);
  return created;
}

let running: Promise<void> | null = null;

async function sync(project: string): Promise<void> {
  // Android 13+ shows the permission prompt only once a channel exists.
  if (Platform.OS === "android")
    await Notifications.setNotificationChannelAsync("attention", {
      name: "Lonora",
      importance: Notifications.AndroidImportance.HIGH,
    });
  let permission = await Notifications.getPermissionsAsync();
  if (!permission.granted && permission.canAskAgain)
    permission = await Notifications.requestPermissionsAsync();
  const device = await deviceId();
  if (!permission.granted) {
    // The owner turned notifications off: the server stops pushing to this phone.
    await api.delete(`/push/devices/${device}`).catch((error: unknown) => {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    });
    return;
  }
  const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId: project });
  await api.put(`/push/devices/${device}`, {
    token,
    platform: Platform.OS === "ios" ? "ios" : "android",
  });
}

export function syncPushDevice(): Promise<void> {
  const project = projectId();
  if (!project) return Promise.resolve();
  running ??= sync(project).finally(() => {
    running = null;
  });
  return running;
}

export function onPushTokenChange(listener: () => void): () => void {
  const subscription = Notifications.addPushTokenListener(listener);
  return () => subscription.remove();
}

export type PushTarget = { threadId: string; around: number | null };

// The push carries only the conversation and the card's position in it (no price, no
// volume, no account): the tap opens the conversation, where the fixed card reads the live
// record. A push has no action button and never approves anything.
function target(response: Notifications.NotificationResponse | null): PushTarget | null {
  const data = response?.notification.request.content.data;
  const threadId = data?.thread_id;
  if (typeof threadId !== "string" || !threadId) return null;
  const around = data?.around;
  return {
    threadId,
    around: typeof around === "number" && Number.isInteger(around) && around > 0 ? around : null,
  };
}

export function onPushOpened(open: (target: PushTarget) => void): () => void {
  const handle = (response: Notifications.NotificationResponse | null) => {
    // Cleared once handled: a later sign-in or reload never replays an old tap.
    Notifications.clearLastNotificationResponse();
    const value = target(response);
    if (value) open(value);
  };
  // The tap that launched the app, then every later tap.
  const launched = Notifications.getLastNotificationResponse();
  if (launched) handle(launched);
  const subscription = Notifications.addNotificationResponseReceivedListener(handle);
  return () => subscription.remove();
}
