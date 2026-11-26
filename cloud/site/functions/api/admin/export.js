// GET /api/admin/export: every account as CSV for staff. Cells that a spreadsheet would run as a
// formula are neutralised.
import { audit } from "../../_lib/core.js";

const COLUMNS = ["id", "email", "name", "country", "lang", "broker", "uses", "status", "created_at", "decided_at", "decided_by", "reason"];

export function csvCell(value) {
  let s = value === null || value === undefined ? "" : String(value);
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\r\n]/.test(s) || s.startsWith("'") ? `"${s.replace(/"/g, '""')}"` : s;
}

export async function onRequestGet({ env, data }) {
  const { results } = await env.DB.prepare(`SELECT ${COLUMNS.join(", ")} FROM accounts ORDER BY created_at`).all();
  const lines = [COLUMNS.join(",")].concat(results.map((r) => COLUMNS.map((c) => csvCell(r[c])).join(",")));
  await audit(env, data.staff, "exported", null, { rows: results.length });
  return new Response(`﻿${lines.join("\r\n")}\r\n`, {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": 'attachment; filename="lonora-accounts.csv"',
      "cache-control": "no-store",
    },
  });
}
