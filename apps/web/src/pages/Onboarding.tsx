import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { auth, type Owner } from "../lib/auth";
import { initializeOwner } from "../lib/bootstrap";
import { userError } from "../lib/user_error";
export function Onboarding({ onLogin }: { onLogin: (owner: Owner) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  return (
    <main className="auth-card">
      <div className="brand-mark">L</div>
      <h1>
        <Trans>Your Lonora workspace</Trans>
      </h1>
      <p>
        <Trans>
          Create the owner account using the setup token from your server configuration.
        </Trans>
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await initializeOwner(email, password, token);
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
            dir="ltr"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          <Trans>Password · at least 12 characters</Trans>
          <input
            type="password"
            minLength={12}
            required
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label>
          <Trans>Setup token</Trans>
          <input
            type="password"
            autoComplete="off"
            required
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </label>
        {error != null && <p role="alert">{userError(error)}</p>}
        <button type="submit" className="primary" disabled={busy}>
          <Trans>Create workspace</Trans>
        </button>
      </form>
    </main>
  );
}
