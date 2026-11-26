// Every /api/admin/* request must carry a valid Cloudflare Access token of an allowed staff email.
import { json, staffEmail } from "../../_lib/core.js";

export async function onRequest(context) {
  const email = await staffEmail(context.request, context.env);
  if (!email) return json({ ok: false, error: "staff_only" }, 403);
  context.data.staff = email;
  return context.next();
}
