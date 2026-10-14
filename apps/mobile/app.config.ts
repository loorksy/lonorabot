import { brand } from "@lonora/ui-tokens/brand";
import type { ExpoConfig } from "expo/config";

const config: ExpoConfig = {
  name: brand.name,
  slug: brand.slug,
  version: "0.2.3",
  scheme: brand.scheme,
  orientation: "portrait",
  userInterfaceStyle: "dark",
  ios: { supportsTablet: true, bundleIdentifier: brand.applicationId },
  android: { package: brand.applicationId, versionCode: 4 },
  web: { bundler: "metro", output: "single", name: brand.name },
  plugins: ["expo-router", "expo-secure-store", "./plugins/with-release-signing.cjs"],
  experiments: { typedRoutes: true },
};

export default config;
