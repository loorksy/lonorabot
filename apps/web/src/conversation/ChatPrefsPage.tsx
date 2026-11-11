import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { ToggleRow } from "../shell/settings/ui";
import { setChatPref, useChatPrefs } from "./prefs";

/* «تجربة المحادثة» (reference chatPrefsPage, Desktop-37 5753-5762): per-device chat
   preferences, applied to every conversation, in the reference's sections and order.
   «حالة الوكيل التفصيلية» is off by default (Q35). */
export function ChatPrefsPage() {
  const prefs = useChatPrefs();
  return (
    <>
      <p className="muted">
        <Trans>Choose how replies appear and how you write. Applies to every conversation.</Trans>
      </p>
      <h3>
        <Trans>Replies</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`Stream the reply word by word`}
          sub={t`The reply appears as it is written, with a «Stop» button`}
          on={prefs.stream}
          onChange={(next) => setChatPref("stream", next)}
        />
        <ToggleRow
          title={t`The agent's work steps`}
          sub={t`Searching, reading sources and running skills inside the message`}
          on={prefs.steps}
          onChange={(next) => setChatPref("steps", next)}
        />
        <ToggleRow
          title={t`Open the steps automatically`}
          sub={t`The steps stay open instead of folding into one line`}
          on={prefs.stepsOpen}
          disabled={!prefs.steps}
          onChange={(next) => setChatPref("stepsOpen", next)}
        />
        <ToggleRow
          title={t`Formatted replies`}
          sub={t`Headings, lists, tables and code with a copy button`}
          on={prefs.markdown}
          onChange={(next) => setChatPref("markdown", next)}
        />
      </div>
      <h3>
        <Trans>Interactive interfaces</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`Interactive elements in replies`}
          sub={t`Calculators, forms, charts and choices the agent sends when they are clearer than text`}
          on={prefs.genui}
          onChange={(next) => setChatPref("genui", next)}
        />
        <ToggleRow
          title={t`Why this interface`}
          sub={t`The «Why this interface?» button explains the agent's decision`}
          on={prefs.genuiWhy}
          disabled={!prefs.genui}
          onChange={(next) => setChatPref("genuiWhy", next)}
        />
      </div>
      <h3>
        <Trans>Agents</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`Detailed agent status`}
          sub={t`Under the agent's name: analysing, searching, watching, waiting for the broker, waiting for your decision, paused, unconfirmed operation — and its picture changes with it. When off, only «Active» shows`}
          on={prefs.agentStatus}
          onChange={(next) => setChatPref("agentStatus", next)}
        />
      </div>
      <h3>
        <Trans context="settings section">Writing</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`Send with Enter`}
          sub={t`On a computer; Shift+Enter for a new line. When off: Ctrl+Enter`}
          on={prefs.enterSend}
          onChange={(next) => setChatPref("enterSend", next)}
        />
        <ToggleRow
          title={t`@ suggestions`}
          sub={t`The list of agents while you write`}
          on={prefs.assist}
          onChange={(next) => setChatPref("assist", next)}
        />
      </div>
      <h3>
        <Trans>Touch</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`Vibration`}
          sub={t`A light vibration on long-press, selection and send`}
          on={prefs.haptics}
          onChange={(next) => setChatPref("haptics", next)}
        />
      </div>
    </>
  );
}
