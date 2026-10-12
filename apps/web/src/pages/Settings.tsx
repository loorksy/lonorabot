import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { IntegrationsSettings } from "../components/settings/IntegrationsSettings";
import { McpSettings } from "../components/settings/McpSettings";
import { ModelsSettings } from "../components/settings/ModelsSettings";
import { OverviewSettings } from "../components/settings/OverviewSettings";
import { SettingsSidebar, type SettingsTab } from "../components/settings/SettingsSidebar";
import { TokenUsage } from "../components/settings/TokenUsage";
import { TradingSettings } from "../components/settings/TradingSettings";
import { VoiceSettings } from "../components/settings/VoiceSettings";
export function Settings() {
  const [tab, setTab] = useState<SettingsTab>("overview");
  return (
    <section>
      <h1>
        <Trans>Settings</Trans>
      </h1>
      <div className="settings-layout">
        <SettingsSidebar selected={tab} onSelect={setTab} />
        <div>
          {tab === "overview" ? (
            <OverviewSettings />
          ) : tab === "models" ? (
            <ModelsSettings />
          ) : tab === "voice" ? (
            <VoiceSettings />
          ) : tab === "trading" ? (
            <TradingSettings />
          ) : tab === "integrations" ? (
            <IntegrationsSettings />
          ) : tab === "mcp" ? (
            <McpSettings />
          ) : (
            <TokenUsage />
          )}
        </div>
      </div>
    </section>
  );
}
