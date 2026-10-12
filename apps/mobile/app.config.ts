import type { ExpoConfig } from "expo/config";

const config: ExpoConfig = {
  name: "Lonora",
  slug: "lonora",
  version: "0.2.0",
  scheme: "lonora",
  orientation: "portrait",
  userInterfaceStyle: "dark",
  ios: { supportsTablet: true, bundleIdentifier: "ai.lonora.mobile" },
  android: { package: "ai.lonora.mobile" },
  web: { bundler: "metro", output: "single", name: "Lonora" },
  plugins: ["expo-router", "expo-secure-store"],
  experiments: { typedRoutes: true },
};

export default config;
