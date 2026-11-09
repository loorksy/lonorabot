/// <reference types="vite/client" />
declare module "*.po" {
  export const messages: Record<string, string>;
}

/** The id of this web build (vite.config.ts); GET /api/version reports the served one. */
declare const __LONORA_BUILD__: string;
