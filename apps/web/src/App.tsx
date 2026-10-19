import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { ApiError, isRequestCancelled, resetSessionRequests } from "./lib/api";
import { auth, type Owner } from "./lib/auth";
import { onboardingStatus } from "./lib/bootstrap";
import { userError } from "./lib/user_error";
import { Auth } from "./pages/Auth";
import { Onboarding } from "./pages/Onboarding";
import { Shell } from "./pages/Shell";
import { ClientProvider } from "./providers/ClientProvider";
export default function App() {
  const [owner, setOwner] = useState<Owner | null>(null);
  const [initialized, setInitialized] = useState<boolean>();
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    const expired = () => {
      resetSessionRequests();
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
    return initialized ? (
      <Auth onLogin={setOwner} />
    ) : (
      <Onboarding
        onLogin={(account) => {
          setInitialized(true);
          setOwner(account);
        }}
      />
    );
  return (
    <ClientProvider key={owner.id} owner={owner}>
      <Shell onLogout={() => setOwner(null)} />
    </ClientProvider>
  );
}
