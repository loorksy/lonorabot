import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

export async function loadSetting(key: string): Promise<string | null> {
  if (Platform.OS === "web") {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(key);
}

export async function saveSetting(key: string, value: string | null): Promise<void> {
  if (Platform.OS === "web") {
    if (value === null) globalThis.localStorage?.removeItem(key);
    else globalThis.localStorage?.setItem(key, value);
    return;
  }
  if (value === null) await SecureStore.deleteItemAsync(key);
  else await SecureStore.setItemAsync(key, value);
}

// Browser sessions are HttpOnly cookies; never place a bearer token in browser storage.
export async function loadNativeToken(): Promise<string | null> {
  return Platform.OS === "web" ? null : SecureStore.getItemAsync("lonora.session");
}

export async function saveNativeToken(value: string | null): Promise<void> {
  if (Platform.OS === "web") return;
  if (value === null) await SecureStore.deleteItemAsync("lonora.session");
  else await SecureStore.setItemAsync("lonora.session", value);
}
