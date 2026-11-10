import { useState } from "react";
import { ModelSettingsOverlay } from "./ModelSettingsOverlay";
import { SettingsSidebar, type SettingsTab } from "./settings-sidebar";
import { TradingSettingsPanel } from "./TradingSettingsPanel";
import { VoiceSettingsOverlay } from "./VoiceSettingsOverlay";
export function SettingsOverlay({ initialTab = "models" }: { initialTab?: SettingsTab }) {
  const [tab, setTab] = useState<SettingsTab>(initialTab);
  return (
    <section>
      <div className="settings-layout">
        <SettingsSidebar selected={tab} onSelect={setTab} />
        <div>
          {tab === "models" ? (
            <ModelSettingsOverlay />
          ) : tab === "voice" ? (
            <VoiceSettingsOverlay />
          ) : (
            <TradingSettingsPanel />
          )}
        </div>
      </div>
    </section>
  );
}
