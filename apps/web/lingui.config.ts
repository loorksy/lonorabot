import { defineConfig } from "@lingui/cli";
export default defineConfig({
  locales: ["ar", "en"],
  sourceLocale: "en",
  catalogs: [
    {
      path: "src/i18n/locales/{locale}/messages",
      include: ["src", "../../packages/ui-web/src", "../../packages/chat-ui/src"],
    },
  ],
});
