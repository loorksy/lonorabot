import { Trans } from "@lingui/react/macro";
import { Icon, type IconName } from "@lonora/ui-web";
import { Component, type ReactNode } from "react";
import { useNavigation } from "./navigation";

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

export function MaintenanceOverlay({ retry }: { retry: () => void }) {
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
          <button type="button" className="btn primary" onClick={retry}>
            <Trans>Try again</Trans>
          </button>
        }
      />
    </div>
  );
}
