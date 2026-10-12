import { Trans } from "@lingui/react/macro";
export type SettingsTab =
  | "overview"
  | "models"
  | "voice"
  | "trading"
  | "integrations"
  | "mcp"
  | "usage";
export function SettingsSidebar({
  selected,
  onSelect,
}: {
  selected: SettingsTab;
  onSelect: (tab: SettingsTab) => void;
}) {
  const tabs: [SettingsTab, React.ReactNode][] = [
    ["overview", <Trans key="367">Appearance</Trans>],
    ["models", <Trans key="410">Global models</Trans>],
    ["voice", <Trans key="455">Voice</Trans>],
    ["trading", <Trans key="494">Trading</Trans>],
    ["integrations", <Trans key="540">Integrations</Trans>],
    ["mcp", <Trans key="582">MCP servers</Trans>],
    ["usage", <Trans key="625">Token usage</Trans>],
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
