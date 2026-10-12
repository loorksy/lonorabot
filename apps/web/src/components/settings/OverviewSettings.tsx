import { Trans } from "@lingui/react/macro";
import { useTheme } from "../../hooks/useTheme";
import { activateLocale, i18n } from "../../i18n/config";
import { useClient } from "../../providers/ClientProvider";
export function OverviewSettings() {
  const { theme, setTheme } = useTheme();
  const { owner, connected } = useClient();
  return (
    <section className="card">
      <h2>
        <Trans>Appearance and workspace</Trans>
      </h2>
      <label>
        <Trans>Language</Trans>
        <select
          value={i18n.locale}
          onChange={(e) => activateLocale(e.target.value === "en" ? "en" : "ar")}
        >
          <option value="ar">العربية</option>
          <option value="en">English</option>
        </select>
      </label>
      <label>
        <Trans>Theme</Trans>
        <select
          value={theme}
          onChange={(e) => setTheme(e.target.value === "light" ? "light" : "dark")}
        >
          <option value="dark">
            <Trans>Dark</Trans>
          </option>
          <option value="light">
            <Trans>Light</Trans>
          </option>
        </select>
      </label>
      <p>
        <bdi>{owner.email}</bdi>
      </p>
      <p role="status">
        {connected ? (
          <Trans>Live connection active</Trans>
        ) : (
          <Trans>Reconnecting to live updates</Trans>
        )}
      </p>
    </section>
  );
}
