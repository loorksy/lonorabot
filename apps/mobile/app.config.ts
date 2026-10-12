import { brand } from "@lonora/ui-tokens/brand";
import type { ExpoConfig } from "expo/config";

const config: ExpoConfig = {
  name: brand.name,
  slug: brand.slug,
  version: "0.2.0",
  scheme: brand.scheme,
  orientation: "portrait",
  userInterfaceStyle: "dark",
  ios: { supportsTablet: true, bundleIdentifier: brand.applicationId },
  android: { package: brand.applicationId },
  web: { bundler: "metro", output: "single", name: brand.name },
  plugins: ["expo-router", "expo-secure-store"],
  experiments: { typedRoutes: true },
};

export default config;
