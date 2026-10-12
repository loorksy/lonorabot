import { useState } from "react";
import { IntegrationSetup } from "../components/integrations/IntegrationSetup";
import { LocalSettings } from "./LocalSettings";
import { McpServersOverlay } from "./McpServersOverlay";
import { ModelSettingsOverlay } from "./ModelSettingsOverlay";
import { SettingsSidebar, type SettingsTab } from "./settings-sidebar";
import { TradingSettingsPanel } from "./TradingSettingsPanel";
import { UsageSettingsPanel } from "./UsageSettingsPanel";
import { VoiceSettingsOverlay } from "./VoiceSettingsOverlay";
export function SettingsOverlay({ initialTab = "overview" }: { initialTab?: SettingsTab }) {
  const [tab, setTab] = useState<SettingsTab>(initialTab);
  return (
    <section>
      <div className="settings-layout">
        <SettingsSidebar selected={tab} onSelect={setTab} />
        <div>
          {tab === "overview" ? (
            <LocalSettings />
          ) : tab === "models" ? (
            <ModelSettingsOverlay />
          ) : tab === "voice" ? (
            <VoiceSettingsOverlay />
          ) : tab === "trading" ? (
            <TradingSettingsPanel />
          ) : tab === "integrations" ? (
            <IntegrationSetup />
          ) : tab === "mcp" ? (
            <McpServersOverlay />
          ) : (
            <UsageSettingsPanel />
          )}
        </div>
      </div>
    </section>
  );
}
