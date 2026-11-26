// Public settings the static pages need: only the Turnstile site key, which is public by design.
import { json } from "../_lib/core.js";

export function onRequestGet({ env }) {
  return json({ turnstile_site_key: env.TURNSTILE_SITE_KEY || null });
}
