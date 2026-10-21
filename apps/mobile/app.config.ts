// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Public OTA native build inputs, never credentials.
import { brand } from "@lonora/ui-tokens/brand";
import type { ExpoConfig } from "expo/config";

const updateUrl = process.env.LONORA_OTA_URL ?? "https://lonora.lork.cloud/api/mobile/updates";
if (!/^https:\/\/[^/?#]+(?:\/[^?#]*)?$/.test(updateUrl))
  throw new Error("LONORA_OTA_URL must be a public HTTPS update endpoint.");
const channel = process.env.LONORA_OTA_CHANNEL ?? "production";
if (!["preview", "production"].includes(channel))
  throw new Error("LONORA_OTA_CHANNEL must be preview or production.");

const config: ExpoConfig = {
  name: brand.name,
  slug: brand.slug,
  version: "0.2.8",
  icon: "./assets/brand/icon-light.png",
  scheme: brand.scheme,
  orientation: "portrait",
  userInterfaceStyle: "dark",
  ios: {
    icon: {
      light: "./assets/brand/icon-light.png",
      dark: "./assets/brand/icon-dark.png",
      tinted: "./assets/brand/icon-tinted.png",
    },
    supportsTablet: true,
    bundleIdentifier: brand.applicationId,
    associatedDomains: [`webcredentials:${new URL(updateUrl).hostname}`],
    infoPlist: {
      NSMicrophoneUsageDescription:
        "السماح لـ Lonora باستخدام الميكروفون للمكالمات مع وكيلك. Allow Lonora to use your microphone for agent calls.",
    },
  },
  android: {
    package: brand.applicationId,
    versionCode: 26102101,
    adaptiveIcon: {
      foregroundImage: "./assets/brand/adaptive-foreground.png",
      monochromeImage: "./assets/brand/adaptive-monochrome.png",
      backgroundColor: "#000000",
    },
    softwareKeyboardLayoutMode: "resize",
    permissions: ["RECORD_AUDIO", "MODIFY_AUDIO_SETTINGS", "WAKE_LOCK"],
    // Attachments use the system document picker and app cache; no overlays or shared storage.
    blockedPermissions: [
      "android.permission.CAMERA",
      "android.permission.SYSTEM_ALERT_WINDOW",
      "android.permission.READ_EXTERNAL_STORAGE",
      "android.permission.WRITE_EXTERNAL_STORAGE",
    ],
  },
  runtimeVersion: { policy: "fingerprint" },
  updates: {
    enabled: true,
    url: updateUrl,
    requestHeaders: { "expo-channel-name": channel },
    checkAutomatically: "ON_LOAD",
    fallbackToCacheTimeout: 0,
    useEmbeddedUpdate: true,
    codeSigningCertificate: "./certificates/ota.pem",
    codeSigningMetadata: { keyid: "main", alg: "rsa-v1_5-sha256" },
  },
  web: {
    bundler: "metro",
    output: "single",
    name: brand.name,
    favicon: "./assets/brand/favicon.png",
  },
  plugins: ["expo-router", "expo-secure-store", "./plugins/with-release-signing.cjs"],
  experiments: { typedRoutes: true },
};

export default config;
