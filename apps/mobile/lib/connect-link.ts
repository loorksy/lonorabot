// The "Open in the app" link of Lonora Cloud's account page (docs/cloud PHASES.md P1-T8, D9):
//   lonora://connect?server=https://<handle>.<domain>[&token=<one-time setup token>]
// The app shows the host and connects only after the owner confirms. A remote server must use
// https; plain http is accepted only for local addresses (a self-hosted install at home).

const TOKEN = /^[A-Za-z0-9_-]{20,128}$/;

function isLocalHost(host: string): boolean {
  if (host === "localhost" || host.endsWith(".local") || host === "[::1]") return true;
  const parts = host.split(".").map(Number);
  if (parts.length !== 4 || parts.some((p) => !Number.isInteger(p) || p < 0 || p > 255))
    return false;
  const [a, b] = parts as [number, number, number, number];
  return a === 127 || a === 10 || (a === 192 && b === 168) || (a === 172 && b >= 16 && b <= 31);
}

export type ConnectLink = { server: string; host: string; token: string | null };

export function parseConnectLink(server: unknown, token: unknown): ConnectLink | null {
  if (typeof server !== "string" || server.length > 300) return null;
  let url: URL;
  try {
    url = new URL(server);
  } catch {
    return null;
  }
  if (url.username || url.password || url.search || url.hash) return null;
  if (url.protocol !== "https:" && !(url.protocol === "http:" && isLocalHost(url.hostname)))
    return null;
  const clean = url.toString().replace(/\/$/, "");
  const t = typeof token === "string" && TOKEN.test(token) ? token : null;
  return { server: clean, host: url.host, token: t };
}

// Whether two addresses name the same server (the same rule as the session's own address).
export function sameServer(a: string, b: string): boolean {
  const key = (value: string) => {
    try {
      return new URL(value.trim())
        .toString()
        .replace(/\/api\/?$/, "")
        .replace(/\/$/, "");
    } catch {
      return null;
    }
  };
  const k = key(a);
  return k !== null && k === key(b);
}

// The token waits here, in memory only, with the server it was issued for, until the sign-in
// screen's setup form takes it. It is never handed to another server.
export type HeldSetupToken = { server: string; token: string };
let pending: HeldSetupToken | null = null;
export function holdSetupToken(server: string, token: string | null) {
  pending = token ? { server, token } : null;
}
export function takeSetupToken(): HeldSetupToken | null {
  const held = pending;
  pending = null;
  return held;
}
