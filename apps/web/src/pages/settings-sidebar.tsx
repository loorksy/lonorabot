import { Trans } from "@lingui/react/macro";
/* The settings screens that have no page in the reference layout yet (model routing, voice,
   the trading controls). Everything else lives on the phase 5 settings pages. */
export type SettingsTab = "models" | "voice" | "trading";
export function SettingsSidebar({
  selected,
  onSelect,
}: {
  selected: SettingsTab;
  onSelect: (tab: SettingsTab) => void;
}) {
  const tabs: [SettingsTab, React.ReactNode][] = [
    ["models", <Trans key="410">Global models</Trans>],
    ["voice", <Trans key="455">Voice</Trans>],
    ["trading", <Trans key="494">Trading</Trans>],
  ];
  return (
    <nav className="settings-nav">
      {tabs.map(([key, label]) => (
        <button
          type="button"
          className={selected === key ? "selected" : ""}
          onClick={() => onSelect(key)}
          key={key}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
