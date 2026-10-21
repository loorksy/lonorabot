import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { auth, type Owner } from "../lib/auth";
import { userError } from "../lib/user_error";
export function Auth({ onLogin }: { onLogin: (owner: Owner) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  return (
    <main className="auth-card">
      <img className="brand-mark" src="/brand/logo.svg" alt="" width="54" height="54" />
      <h1>Lonora</h1>
      <p>
        <Trans>Sign in to your persistent workspace</Trans>
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            onLogin((await auth.login(email, password)).owner);
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          <Trans>Email</Trans>
          <input
            type="email"
            dir="ltr"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          <Trans>Password</Trans>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error != null && <p role="alert">{userError(error)}</p>}
        <button type="submit" className="primary" disabled={busy}>
          <Trans>Sign in</Trans>
        </button>
      </form>
    </main>
  );
}
