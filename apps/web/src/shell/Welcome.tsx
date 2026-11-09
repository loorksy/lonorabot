import { Trans } from "@lingui/react/macro";
import { Icon, type IconName } from "@lonora/ui-web";
import type { ReactNode } from "react";
import { LogoMark } from "./LogoMark";

function ActionRow({
  icon,
  label,
  onClick,
}: {
  icon: IconName;
  label: ReactNode;
  onClick: () => void;
}) {
  return (
    <button type="button" className="row" onClick={onClick}>
      <span className="row-icon">
        <Icon name={icon} />
      </span>
      <span className="body">
        <strong>{label}</strong>
      </span>
      <span className="chevron">
        <Icon name="chev" />
      </span>
    </button>
  );
}
/* Desktop home: the welcome pane in the content column while the chats tab is open (rows, not pills). */
export function Welcome({
  name,
  onNewChat,
  onNewTask,
  onNewGroup,
  onUpdates,
}: {
  name: string;
  onNewChat: () => void;
  onNewTask: () => void;
  onNewGroup: () => void;
  onUpdates: () => void;
}) {
  return (
    <div className="welcome">
      <div className="arcs" aria-hidden="true" />
      <span className="logo-hero">
        <LogoMark size={64} />
      </span>
      <h2>
        <Trans>Welcome {name}</Trans>
      </h2>
      <p>
        <Trans>What shall we do today with your agents?</Trans>
      </p>
      <div className="group welcome-list">
        <ActionRow icon="chat" label={<Trans>New chat</Trans>} onClick={onNewChat} />
        <ActionRow icon="task" label={<Trans>New task</Trans>} onClick={onNewTask} />
        <ActionRow icon="users" label={<Trans>New group</Trans>} onClick={onNewGroup} />
        <ActionRow icon="bell" label={<Trans>Updates</Trans>} onClick={onUpdates} />
      </div>
      <small>
        <Icon name="shield" /> <Trans>Permissions are independent for each agent</Trans>
      </small>
    </div>
  );
}
