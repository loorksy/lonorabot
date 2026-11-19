import { plural, t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentPermissionLevel, PermissionState } from "@lonora/contracts";
import { Icon, type IconName } from "@lonora/ui-web";
import { type ReactNode, useCallback, useState } from "react";
import type { Agent } from "../lib/api";
import { domainApi } from "../shell/domain/api";
import { useLoad } from "../shell/domain/hooks";
import { useNavigation } from "../shell/navigation";
import { useLinkedCount } from "../shell/settings/SettingsRoot";
import { useSheets } from "../shell/sheets/SheetHost";
import { LEVEL_ICON, levelName } from "./PermissionMenu";

/* «إضافة إلى المحادثة» (reference toolsSheet, Desktop-37 4978-5009): tiles ملفات · صور · كاميرا;
   مهمة جديدة · جدولة; الصلاحية · الشارت; البحث في الويب (switch) · التكاملات · المهارات ·
   المعرفة, each with its count. A Claude-style bar sheet. */
export type ToolsInput = {
  agent?: Agent;
  isGroup: boolean;
  /** A group's lead (or first member): the new task's preselected agent. */
  groupLead?: string;
  trading: boolean;
  permission: PermissionState | null;
  permissionFailed?: boolean;
  webSearch: boolean;
  onWebSearch: (on: boolean) => Promise<void> | void;
  onFiles: () => void;
  onPhotos: (camera: boolean) => void;
};

const linkedText = (count: number) =>
  count === 0
    ? t({ message: "Not linked", context: "integrations" })
    : plural(count, {
        one: "one linked",
        two: "two linked",
        few: "# linked",
        many: "# linked",
        other: "# linked",
      });
const skillsText = (count: number) =>
  count === 0
    ? t`No skills enabled`
    : plural(count, {
        one: "one skill enabled",
        two: "two skills enabled",
        few: "# skills enabled",
        many: "# skills enabled",
        other: "# skills enabled",
      });
const knowledgeText = (count: number) =>
  count === 0
    ? t({ message: "Empty", context: "knowledge" })
    : plural(count, {
        one: "one item",
        two: "two items",
        few: "# items",
        many: "# items",
        other: "# items",
      });

function AddRow({
  icon,
  title,
  sub,
  onClick,
  end,
  role,
  checked,
}: {
  icon: IconName;
  title: ReactNode;
  sub?: ReactNode;
  onClick: () => void;
  end?: ReactNode;
  role?: "switch";
  checked?: boolean;
}) {
  return (
    // biome-ignore lint/a11y/useAriaPropsSupportedByRole: aria-checked is only set with role="switch"
    <button type="button" className="add-row" role={role} aria-checked={checked} onClick={onClick}>
      <span className="add-ic">
        <Icon name={icon} />
      </span>
      <span className="add-body">
        <strong>{title}</strong>
        {sub ? <small>{sub}</small> : null}
      </span>
      {end ?? (
        <span className="add-end">
          <Icon name="chev" />
        </span>
      )}
    </button>
  );
}

function ToolsBody({
  input,
  close,
  nav,
}: {
  input: ToolsInput;
  close: () => void;
  nav: { go: (path: string) => void };
}) {
  const [web, setWeb] = useState(input.webSearch);
  // Until the level is read (or when it cannot be), the row says so: never a guessed level.
  const level: AgentPermissionLevel | null = input.permission?.effective_level ?? null;
  const go = (path: string) => {
    close();
    nav.go(path);
  };
  const agentId = input.agent && !input.isGroup ? input.agent.id : null;
  const agentQuery = agentId ? `?agent=${encodeURIComponent(agentId)}` : "";
  // Each count shows once read, never a guessed zero.
  const linked = useLinkedCount();
  const skills = useLoad(agentId ? () => domainApi.skills(agentId) : null, `skills:${agentId}`);
  const knowledge = useLoad(
    agentId ? () => domainApi.knowledge(agentId) : null,
    `knowledge:${agentId}`,
  );
  return (
    <>
      <div className="add-tiles">
        {(
          [
            [
              "fileUp",
              t({ message: "Files", context: "add to the conversation" }),
              () => input.onFiles(),
            ],
            ["image", t`Photos`, () => input.onPhotos(false)],
            ["camera", t`Camera`, () => input.onPhotos(true)],
          ] as const
        ).map(([icon, label, run]) => (
          <button
            key={icon}
            type="button"
            className="add-tile"
            onClick={() => {
              close();
              run();
            }}
          >
            <span className="add-ic">
              <Icon name={icon} />
            </span>
            <span>{label}</span>
          </button>
        ))}
      </div>
      <div className="add-group">
        <AddRow
          icon="task"
          title={<Trans>New task</Trans>}
          sub={<Trans>The agent follows it until it is done</Trans>}
          onClick={() => {
            // A group's new task starts with its lead agent.
            const taskAgent = agentId ?? input.groupLead;
            go(`/app/new-task${taskAgent ? `?agent=${encodeURIComponent(taskAgent)}` : ""}`);
          }}
        />
        <AddRow
          icon="clock"
          title={t({ message: "Schedule", context: "add to the conversation" })}
          sub={<Trans>One time or repeating</Trans>}
          onClick={() => go(`/app/new-schedule${agentQuery}`)}
        />
      </div>
      <div className="add-group">
        {input.isGroup ? (
          <AddRow
            icon="shield"
            title={<Trans>Members' permissions</Trans>}
            sub={<Trans>Each agent has its own permissions</Trans>}
            onClick={() => {
              close();
              window.dispatchEvent(new CustomEvent("lonora:members-permissions"));
            }}
          />
        ) : input.trading ? (
          <AddRow
            icon={level ? LEVEL_ICON[level] : input.permissionFailed ? "alert" : "shield"}
            title={<Trans>Permission</Trans>}
            sub={level ? levelName(level) : input.permissionFailed ? t`Permission unknown` : "…"}
            onClick={() => {
              close();
              requestAnimationFrame(() =>
                document.querySelector<HTMLButtonElement>(".composer .mode-chip")?.click(),
              );
            }}
          />
        ) : null}
        {(input.isGroup || input.trading) && (
          <AddRow
            icon="chart"
            title={<Trans>Chart</Trans>}
            sub={input.agent?.trading_symbol ?? t`The market`}
            onClick={() => {
              close();
              window.dispatchEvent(new CustomEvent("lonora:open-chart"));
            }}
          />
        )}
      </div>
      <div className="add-group">
        <AddRow
          icon="globe"
          title={<Trans>Web search</Trans>}
          sub={web ? <Trans>Gathers sources before replying</Trans> : undefined}
          role="switch"
          checked={web}
          end={<span className="switch" aria-hidden="true" />}
          onClick={() => {
            const next = !web;
            setWeb(next);
            void input.onWebSearch(next);
          }}
        />
        <AddRow
          icon="plug"
          title={<Trans>Integrations</Trans>}
          sub={linked === null ? undefined : linkedText(linked)}
          onClick={() => go("/app/integrations")}
        />
        {!input.isGroup && (
          <>
            <AddRow
              icon="bolt"
              title={<Trans>Skills</Trans>}
              sub={
                skills.data && skillsText(skills.data.filter((row) => row.payload.enabled).length)
              }
              onClick={() => go(`/app/skills${agentQuery}`)}
            />
            <AddRow
              icon="book"
              title={<Trans>Knowledge</Trans>}
              sub={knowledge.data && knowledgeText(knowledge.data.length)}
              onClick={() => go(`/app/knowledge${agentQuery}`)}
            />
          </>
        )}
      </div>
    </>
  );
}

export function useToolsSheet() {
  const sheets = useSheets();
  const nav = useNavigation();
  const open = useCallback(
    (input: ToolsInput) => {
      const title = t`Add to the conversation`;
      sheets.open({
        id: "tools",
        bar: true,
        title,
        label: title,
        body: <ToolsBody input={input} close={() => sheets.close()} nav={nav} />,
      });
    },
    [sheets, nav],
  );
  return { open };
}
