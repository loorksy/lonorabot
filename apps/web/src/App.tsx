import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { ApiError, isRequestCancelled, resetSessionRequests } from "./lib/api";
import { auth, type Owner } from "./lib/auth";
import { onboardingStatus } from "./lib/bootstrap";
import { userError } from "./lib/user_error";
import { ClientProvider } from "./providers/ClientProvider";
import { Shell } from "./shell/Shell";
import { AuthFlow } from "./shell/settings/AuthFlow";
export default function App() {
  const [owner, setOwner] = useState<Owner | null>(null);
  const [initialized, setInitialized] = useState<boolean>();
  const [error, setError] = useState<unknown>();
  // «انتهت جلستك»: the server ended the session (not the owner's own sign-out).
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const expired = () => {
      resetSessionRequests();
      setExpired(true);
      setOwner(null);
    };
    window.addEventListener("lonora:session-expired", expired);
    return () => window.removeEventListener("lonora:session-expired", expired);
  }, []);
  useEffect(() => {
    let live = true;
    void onboardingStatus()
      .then(async (status) => {
        let account: Owner | null = null;
        if (status.owner_initialized)
          try {
            account = await auth.session();
          } catch (e) {
            if (!(e instanceof ApiError && e.status === 401)) throw e;
          }
        if (live) {
          setOwner(account);
          setInitialized(status.owner_initialized);
        }
      })
      .catch((failure) => {
        if (live && !isRequestCancelled(failure)) setError(failure);
      });
    return () => {
      live = false;
    };
  }, []);
  if (error != null)
    return (
      <main className="auth-card">
        <p role="alert">{userError(error)}</p>
        <button type="button" onClick={() => location.reload()}>
          <Trans>Retry</Trans>
        </button>
      </main>
    );
  if (initialized === undefined)
    return (
      <main className="workspace-loading" role="status" data-testid="workspace-loading">
        <span className="workspace-loading-mark" aria-hidden="true">
          L
        </span>
        <Trans>Opening workspace…</Trans>
      </main>
    );
  if (!owner)
    return (
      <AuthFlow
        initialized={initialized}
        expired={expired}
        onLogin={(account) => {
          setInitialized(true);
          setExpired(false);
          setOwner(account);
        }}
      />
    );
  try {
    // Signed in once on this device: the intro slides are not shown again after a sign-out.
    localStorage.setItem("lonora.auth.intro-seen", "1");
  } catch {
    /* storage unavailable */
  }
  return (
    <ClientProvider key={owner.id} owner={owner}>
      <Shell
        onLogout={() => {
          setExpired(false);
          setOwner(null);
        }}
      />
    </ClientProvider>
  );
}
