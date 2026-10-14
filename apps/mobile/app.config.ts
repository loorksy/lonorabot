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
  version: "0.2.4",
  scheme: brand.scheme,
  orientation: "portrait",
  userInterfaceStyle: "dark",
  ios: {
    supportsTablet: true,
    bundleIdentifier: brand.applicationId,
    infoPlist: {
      NSMicrophoneUsageDescription:
        "السماح لـ Lonora باستخدام الميكروفون للمكالمات مع وكيلك. Allow Lonora to use your microphone for agent calls.",
    },
  },
  android: {
    package: brand.applicationId,
    versionCode: 5,
    permissions: ["RECORD_AUDIO", "MODIFY_AUDIO_SETTINGS"],
    blockedPermissions: ["android.permission.CAMERA"],
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
  web: { bundler: "metro", output: "single", name: brand.name },
  plugins: ["expo-router", "expo-secure-store", "./plugins/with-release-signing.cjs"],
  experiments: { typedRoutes: true },
};

export default config;
