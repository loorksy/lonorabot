import { t } from "@lingui/core/macro";
import { Icon, type IconName } from "@lonora/ui-web";
import { tabLabel } from "./FloatingTabBar";
import { LogoMark } from "./LogoMark";
import type { Root } from "./routes";

const icons: Record<Root, IconName> = {
  chats: "chat",
  updates: "bell",
  tasks: "task",
  settings: "settings",
};
/* The desktop rail (≥900px): brand, the four sections, the list collapse toggle and the owner. */
export function DesktopRail({
  section,
  chatsBadge,
  updatesDot,
  collapsed,
  onToggleCollapsed,
  onSection,
  ownerInitial,
  onOwner,
}: {
  section: Root;
  chatsBadge: number;
  updatesDot: boolean;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onSection: (root: Root) => void;
  ownerInitial: string;
  onOwner: () => void;
}) {
  const button = (root: Root) => (
    <button
      type="button"
      key={root}
      className={section === root ? "active" : ""}
      data-rail={root}
      aria-label={tabLabel(root)}
      title={tabLabel(root)}
      aria-current={section === root ? "page" : undefined}
      onClick={() => onSection(root)}
    >
      <Icon name={icons[root]} />
      {root === "updates" && updatesDot ? (
        <span className="rail-dot" />
      ) : root === "chats" && chatsBadge ? (
        <span className="rail-badge">{chatsBadge}</span>
      ) : null}
    </button>
  );
  return (
    <aside className="desktop-rail" aria-label={t`Sections`}>
      <span className="rail-brand" title="Lonora">
        <LogoMark size={28} />
      </span>
      {button("chats")}
      {button("updates")}
      {button("tasks")}
      <div className="rail-spacer" />
      <button
        type="button"
        title={t`Collapse or expand the chat list`}
        aria-label={t`Collapse the chat list`}
        aria-expanded={!collapsed}
        onClick={onToggleCollapsed}
      >
        <Icon name="chev" />
      </button>
      {button("settings")}
      <button type="button" title={t`Your profile`} aria-label={t`Your profile`} onClick={onOwner}>
        <span className="avatar initial">{ownerInitial}</span>
      </button>
    </aside>
  );
}
