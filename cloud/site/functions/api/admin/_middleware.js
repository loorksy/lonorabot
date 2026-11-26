// Every /api/admin/* request must come from a staff member signed in at the proxy (core.js staffEmail).
import { json, staffEmail } from "../../_lib/core.js";

export async function onRequest(context) {
  const email = staffEmail(context.request, context.env);
  if (!email) return json({ ok: false, error: "staff_only" }, 403);
  context.data.staff = email;
  return context.next();
}
