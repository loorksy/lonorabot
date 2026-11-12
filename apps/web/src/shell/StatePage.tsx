import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon, type IconName } from "@lonora/ui-web";
import { Component, type ReactNode, useEffect, useRef } from "react";
import { useNavigation } from "./navigation";
import { useToast } from "./Toast";

/* Full states: 404, a page that throws, whole-app maintenance. */
export function StatePage({
  icon,
  title,
  text,
  actions,
  code,
}: {
  icon: IconName;
  title: ReactNode;
  text: ReactNode;
  actions: ReactNode;
  code?: string;
}) {
  return (
    <div className="state-page" role="status">
      <div className="state-art">
        <Icon name={icon} />
        {code && <b>{code}</b>}
      </div>
      <h2>{title}</h2>
      <p>{text}</p>
      <div className="state-actions">{actions}</div>
    </div>
  );
}

export function NotFoundPage() {
  const nav = useNavigation();
  return (
    <StatePage
      icon="search"
      code="404"
      title={<Trans>Page not found</Trans>}
      text={<Trans>This page may have moved or is no longer available.</Trans>}
      actions={
        <>
          <button type="button" className="btn primary" onClick={() => nav.go("/app")}>
            <Trans>Back to chats</Trans>
          </button>
          <button type="button" className="btn outline" onClick={nav.back}>
            <Trans>Back</Trans>
          </button>
        </>
      }
    />
  );
}

function RenderError({ retry }: { retry: () => void }) {
  const nav = useNavigation();
  return (
    <StatePage
      icon="alert"
      title={<Trans>This page could not be displayed</Trans>}
      text={
        <Trans>
          An unexpected error occurred while displaying it. Your data is saved and nothing was lost.
        </Trans>
      }
      actions={
        <>
          <button type="button" className="btn primary" onClick={retry}>
            <Trans>Try again</Trans>
          </button>
          <button type="button" className="btn outline" onClick={nav.back}>
            <Trans>Back</Trans>
          </button>
        </>
      }
    />
  );
}

/** A page that throws renders a calm state instead of a blank screen; navigating resets it. */
export class PageErrorBoundary extends Component<
  { children: ReactNode; resetKey: string },
  { failed: boolean; key: string }
> {
  state = { failed: false, key: this.props.resetKey };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  static getDerivedStateFromProps(
    props: { resetKey: string },
    state: { failed: boolean; key: string },
  ) {
    return props.resetKey !== state.key ? { failed: false, key: props.resetKey } : null;
  }
  componentDidCatch(error: unknown) {
    console.warn("render guard:", error);
  }
  render() {
    return this.state.failed ? (
      <RenderError retry={() => this.setState({ failed: false })} />
    ) : (
      this.props.children
    );
  }
}

/** The API and its database answer (`/health`); a stalled gateway alone does not hide the app. */
const serverAnswers = () =>
  fetch("/health", { credentials: "include" }).then(
    (response) => response.ok,
    () => false,
  );

/* «Lonora قيد الصيانة»: over the whole app while the server does not answer. It leaves by
   itself once the server is back, and «إعادة المحاولة» asks at once. */
export function MaintenanceOverlay({ onReady }: { onReady: () => void }) {
  const toast = useToast();
  const ready = useRef(onReady);
  ready.current = onReady;
  useEffect(() => {
    const timer = window.setInterval(async () => {
      if (document.visibilityState === "visible" && (await serverAnswers())) ready.current();
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);
  const retry = async () => {
    if (await serverAnswers()) return onReady();
    navigator.vibrate?.([10, 50, 10]);
    toast(t`Maintenance is still in progress. Try again shortly`, { type: "warn" });
  };
  return (
    <div id="app-state">
      <StatePage
        icon="settings"
        title={<Trans>Lonora is under maintenance</Trans>}
        text={
          <Trans>
            We are making quick improvements to the service. Your chats are saved and we will be
            back in minutes.
          </Trans>
        }
        actions={
          <button type="button" className="btn primary" onClick={() => void retry()}>
            <Trans>Try again</Trans>
          </button>
        }
      />
    </div>
  );
}
