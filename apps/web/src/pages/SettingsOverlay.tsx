import { useState } from "react";
import { useNavigation } from "../shell/navigation";
import { SettingsSidebar, type SettingsTab } from "./settings-sidebar";
import { TradingSettingsPanel } from "./TradingSettingsPanel";
import { VoiceSettingsOverlay } from "./VoiceSettingsOverlay";
/* «Global models» is the models page (/app/models); its tab here opens it. */
export function SettingsOverlay({ initialTab }: { initialTab: Exclude<SettingsTab, "models"> }) {
  const nav = useNavigation();
  const [tab, setTab] = useState(initialTab);
  return (
    <section>
      <div className="settings-layout">
        <SettingsSidebar
          selected={tab}
          onSelect={(next) => (next === "models" ? nav.go("/app/models") : setTab(next))}
        />
        <div>{tab === "voice" ? <VoiceSettingsOverlay /> : <TradingSettingsPanel />}</div>
      </div>
    </section>
  );
}
