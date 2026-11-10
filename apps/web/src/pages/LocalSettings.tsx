import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { setChatPref, useChatPrefs } from "../conversation/prefs";
import { useTheme } from "../hooks/useTheme";
import { activateLocale, i18n } from "../i18n/config";
import { useClient } from "../providers/ClientProvider";
export function LocalSettings() {
  const { theme, setTheme } = useTheme();
  const { owner, connected } = useClient();
  const prefs = useChatPrefs();
  return (
    <section className="card">
      <h2>
        <Trans>Appearance and workspace</Trans>
      </h2>
      <label>
        <Trans>Language</Trans>
        <select
          aria-label={t`Language`}
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
          aria-label={t`Theme`}
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
      {/* Q35: «حالة الوكيل التفصيلية» is a per-device preference, off by default. */}
      <label className="check">
        <input
          type="checkbox"
          checked={prefs.agentStatus}
          onChange={(event) => setChatPref("agentStatus", event.target.checked)}
        />
        <span>
          <Trans>Detailed agent status</Trans>
          <small>
            <Trans>
              Under the agent's name: analysing, searching, watching, waiting for the broker,
              waiting for your decision, paused, unconfirmed operation.
            </Trans>
          </small>
        </span>
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={prefs.enterSend}
          onChange={(event) => setChatPref("enterSend", event.target.checked)}
        />
        <span>
          <Trans>Send with Enter</Trans>
        </span>
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
