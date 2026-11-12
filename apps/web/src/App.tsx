import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import {
  ApiError,
  isRequestCancelled,
  isServiceUnavailable,
  resetSessionRequests,
} from "./lib/api";
import { auth, type Owner } from "./lib/auth";
import { onboardingStatus } from "./lib/bootstrap";
import { userError } from "./lib/user_error";
import { ClientProvider } from "./providers/ClientProvider";
import { LogoMark } from "./shell/LogoMark";
import { Shell } from "./shell/Shell";
import { MaintenanceOverlay, StatePage } from "./shell/StatePage";
import { AuthFlow } from "./shell/settings/AuthFlow";
import { ToastProvider } from "./shell/Toast";
export default function App() {
  const [owner, setOwner] = useState<Owner | null>(null);
  const [initialized, setInitialized] = useState<boolean>();
  const [error, setError] = useState<unknown>();
  // «انتهت جلستك»: the server ended the session (not the owner's own sign-out).
  const [expired, setExpired] = useState(false);
  // The reference reopens the intro slides when the owner signs out (signOut → authOpen("intro")).
  const [signedOut, setSignedOut] = useState(false);
  // Counts the tries to start: a retry asks the server again, without reloading the page.
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const expired = () => {
      resetSessionRequests();
      setExpired(true);
      setOwner(null);
    };
    window.addEventListener("lonora:session-expired", expired);
    return () => window.removeEventListener("lonora:session-expired", expired);
  }, []);
  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` is the retry trigger
  useEffect(() => {
    let live = true;
    setError(undefined);
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
  }, [attempt]);
  const retry = () => setAttempt((count) => count + 1);
  if (error != null) {
    const offline = navigator.onLine === false;
    return (
      <div className="app-shell">
        {isServiceUnavailable(error) ? (
          <ToastProvider>
            <MaintenanceOverlay onReady={retry} />
          </ToastProvider>
        ) : (
          <div id="app-state">
            <StatePage
              icon={offline ? "wifiOff" : "alert"}
              title={
                offline ? (
                  <Trans>No internet connection</Trans>
                ) : (
                  <Trans>An unexpected error occurred</Trans>
                )
              }
              text={userError(error)}
              actions={
                <button type="button" className="btn primary" onClick={retry}>
                  <Trans>Try again</Trans>
                </button>
              }
            />
          </div>
        )}
      </div>
    );
  }
  if (initialized === undefined)
    return (
      <div className="app-shell">
        <main className="boot" role="status" data-testid="workspace-loading">
          <span className="logo-hero">
            <LogoMark size={64} />
          </span>
          <Trans>Opening workspace…</Trans>
        </main>
      </div>
    );
  if (!owner)
    return (
      <AuthFlow
        initialized={initialized}
        expired={expired}
        intro={signedOut}
        onLogin={(account) => {
          setInitialized(true);
          setExpired(false);
          setSignedOut(false);
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
          setSignedOut(true);
          setOwner(null);
        }}
      />
    </ClientProvider>
  );
}
