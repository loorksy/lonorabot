import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentPermissionLevel, PermissionState } from "@lonora/contracts";
import { Icon, type IconName } from "@lonora/ui-web";
import { type ReactNode, useCallback, useState } from "react";
import type { Agent } from "../lib/api";
import { useNavigation } from "../shell/navigation";
import { useSheets } from "../shell/sheets/SheetHost";
import { LEVEL_ICON, levelName } from "./PermissionMenu";

/* «إضافة إلى المحادثة» (reference toolsSheet, Desktop-37 4978-5009): tiles ملفات · صور · كاميرا;
   مهمة جديدة · جدولة · رسالة صوتية; الصلاحية · الشارت; البحث في الويب (switch) · التكاملات ·
   المهارات · المعرفة. A Claude-style bar sheet. */
export type ToolsInput = {
  agent?: Agent;
  isGroup: boolean;
  trading: boolean;
  permission: PermissionState | null;
  permissionFailed?: boolean;
  webSearch: boolean;
  onWebSearch: (on: boolean) => Promise<void> | void;
  onFiles: () => void;
  onPhotos: (camera: boolean) => void;
  onVoiceNote: () => void;
};

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
  const agentPath = input.agent ? `/app/${encodeURIComponent(input.agent.id)}` : "/app";
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
          onClick={() => go("/app/tasks?new=1")}
        />
        <AddRow
          icon="clock"
          title={t({ message: "Schedule", context: "add to the conversation" })}
          sub={<Trans>One time or repeating</Trans>}
          onClick={() => go("/app/routines")}
        />
        <AddRow
          icon="mic"
          title={<Trans>Voice message</Trans>}
          onClick={() => {
            close();
            input.onVoiceNote();
          }}
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
          onClick={() => go("/app/integrations")}
        />
        {!input.isGroup && (
          <>
            <AddRow
              icon="bolt"
              title={<Trans>Skills</Trans>}
              onClick={() => go(`${agentPath}?settings=skills`)}
            />
            <AddRow
              icon="book"
              title={<Trans>Knowledge</Trans>}
              onClick={() =>
                go(
                  `/app/knowledge${input.agent ? `?agent=${encodeURIComponent(input.agent.id)}` : ""}`,
                )
              }
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
