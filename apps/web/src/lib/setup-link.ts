// The one-time setup link of a new installation: https://<host>/#token=<bootstrap token>
// (docs/cloud PHASES.md P1-T4). The token sits in the URL fragment, which browsers never send to
// the server, and the first-run screen removes it from the address bar and history at once.

const TOKEN = /^[A-Za-z0-9_-]{20,128}$/;

export function setupTokenFromHash(hash: string): string | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  const token = new URLSearchParams(raw).get("token");
  return token && TOKEN.test(token) ? token : null;
}

let taken: string | null | undefined;

/** Reads the token once per page load and clears the fragment from the URL and history. */
export function takeSetupToken(): string | null {
  if (taken !== undefined) return taken;
  taken = null;
  if (typeof window === "undefined") return taken;
  const { hash, pathname, search } = window.location;
  if (!hash) return taken;
  taken = setupTokenFromHash(hash);
  if (new URLSearchParams(hash.slice(1)).has("token")) {
    window.history.replaceState(window.history.state, "", pathname + search);
  }
  return taken;
}
