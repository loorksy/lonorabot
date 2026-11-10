import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { showsTradingControl } from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { type ReactNode, useCallback } from "react";
import { ConversationCharts } from "../components/charts/ConversationCharts";
import { TradingGoals } from "../components/goals/TradingGoals";
import { useChatPrefs } from "../conversation/prefs";
import { useAgentSheet } from "../conversation/sheets/AgentSheet";
import { useWatchesSheet } from "../conversation/sheets/WatchesSheet";
import { useAgentLiveState } from "../lib/agent-live-state";
import type { Agent, Resource } from "../lib/api";
import { GroupSettings } from "../pages/GroupPanel";
import { Knowledge } from "../pages/Knowledge";
import { AgentSettings } from "../pages/shell/bot-settings";
import { useClient } from "../providers/ClientProvider";
import { useShellData } from "./data";
import { useNavigation } from "./navigation";
import { useSheets } from "./sheets/SheetHost";

/* The conversation's ⋮ menu as a bar sheet whose rows open their content as in-sheet pages
   (← back to the menu, the sheet's height morphs). The pages mount the existing panels until
   phases 3 and 4 give them the reference's own layouts. */
type MenuPage = "menu" | "info" | "knowledge" | "goals";

function MenuRow({
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

/** «الحالة والأمان»: trading agents and the status preference always; any other agent while it
    has a task that may need the owner (review, resume). Live, since the menu stays open. */
function StatusRow({
  agent,
  shown,
  onClick,
}: {
  agent: Agent;
  shown: boolean;
  onClick: () => void;
}) {
  const tasks = useAgentLiveState(agent.id).state?.tasks ?? [];
  if (!shown && !tasks.length) return null;
  return <MenuRow icon="shield" label={<Trans>Status and safety</Trans>} onClick={onClick} />;
}

export function useChatMenu({
  agent,
  group,
  memberAgents,
}: {
  agent?: Agent;
  group?: Resource;
  memberAgents: Agent[];
}) {
  const sheets = useSheets();
  const nav = useNavigation();
  const data = useShellData();
  const { refresh } = useClient();
  const prefs = useChatPrefs();
  const statusSheet = useAgentSheet((id) =>
    window.dispatchEvent(new CustomEvent("lonora:jump", { detail: { id } })),
  );
  const watchesSheet = useWatchesSheet();
  // Lonora (the personal agent) trades too (Q19): its chat has the capsule and the sheet's
  // trading section like any trading agent's.
  const trading = Boolean(
    agent &&
      (agent.template === "trading" ||
        showsTradingControl({ role: agent.role, trading_account_id: agent.trading_account_id })),
  );
  // The sheet keeps the body it was opened with: the chart an answer asks for goes in here.
  const openChart = useCallback(
    (chartId?: string) => {
      const title = t`Chart`;
      sheets.open({
        id: "chart",
        expand: true,
        title,
        label: title,
        body: (
          <div className="grow legacy-surface">
            <ConversationCharts
              key={agent?.id ?? group?.id}
              preferredChartId={chartId}
              agentId={agent?.id}
              binding={
                agent?.trading_account_id && agent.trading_symbol
                  ? { accountId: agent.trading_account_id, symbol: agent.trading_symbol }
                  : undefined
              }
              threadId={group?.state?.thread_id ? String(group.state.thread_id) : undefined}
              onOpenMarket={() => nav.go("/app/market")}
            />
          </div>
        ),
      });
    },
    [sheets, nav, agent, group],
  );
  const openPage = useCallback(
    (page: MenuPage, dir?: "fwd" | "back") => {
      const title =
        page === "menu"
          ? t`Chat menu`
          : page === "info"
            ? group
              ? t`Group info`
              : t`Agent info`
            : page === "knowledge"
              ? t`Knowledge`
              : t`Goals`;
      let body: ReactNode;
      if (page === "menu")
        body = (
          <>
            <div className="group">
              <MenuRow
                icon={group ? "users" : "info"}
                label={group ? <Trans>Group info</Trans> : <Trans>Agent info</Trans>}
                onClick={() => openPage("info", "fwd")}
              />
              <MenuRow icon="chart" label={<Trans>Chart</Trans>} onClick={() => openChart()} />
              {agent && (
                <StatusRow
                  agent={agent}
                  shown={trading || prefs.agentStatus}
                  onClick={() => statusSheet(agent, trading, prefs.agentStatus)}
                />
              )}
              {agent && trading && (
                <MenuRow
                  icon="radar"
                  label={<Trans>Watches</Trans>}
                  onClick={() => watchesSheet(agent)}
                />
              )}
              <MenuRow
                icon="book"
                label={<Trans>Knowledge</Trans>}
                onClick={() => openPage("knowledge", "fwd")}
              />
              {agent && (
                <MenuRow
                  icon="target"
                  label={<Trans>Goals</Trans>}
                  onClick={() => openPage("goals", "fwd")}
                />
              )}
              {/* «المهام المجدولة» of this agent (or the group's first member): the page. */}
              <MenuRow
                icon="clock"
                label={<Trans>Scheduled tasks</Trans>}
                onClick={() => {
                  sheets.close();
                  nav.go(`/app/routines?agent=${agent?.id ?? memberAgents[0]?.id ?? ""}`);
                }}
              />
            </div>
            <div className="group">
              <MenuRow
                icon="task"
                label={<Trans>New task</Trans>}
                onClick={() => nav.go("/app/tasks?new=1")}
              />
              <MenuRow
                icon="file"
                label={<Trans>Agent files</Trans>}
                onClick={() => {
                  sheets.close();
                  nav.go(`/app/artifacts${agent ? `?agent=${agent.id}` : ""}`);
                }}
              />
            </div>
          </>
        );
      else if (page === "info")
        body = agent ? (
          <AgentSettings key={agent.id} agent={agent} onClose={() => sheets.close()} />
        ) : group ? (
          <GroupSettings
            key={group.id}
            group={group}
            agents={data.agents}
            onSave={() => {
              refresh();
              sheets.close();
            }}
          />
        ) : null;
      else if (page === "knowledge")
        body = (
          <Knowledge
            key={agent?.id ?? group?.id}
            agents={agent ? data.agents : memberAgents}
            initialAgent={agent?.id ?? memberAgents[0]?.id ?? ""}
          />
        );
      else body = agent ? <TradingGoals agentId={agent.id} /> : null;
      sheets.open(
        {
          id: "chat-menu",
          bar: true,
          title,
          label: title,
          dir,
          back: page === "menu" ? undefined : () => openPage("menu", "back"),
          body: page === "menu" ? body : <div className="legacy-surface">{body}</div>,
        },
        { morph: true },
      );
    },
    [
      sheets,
      nav,
      data,
      group,
      agent,
      memberAgents,
      refresh,
      openChart,
      prefs.agentStatus,
      statusSheet,
      trading,
      watchesSheet,
    ],
  );
  return {
    openMenu: () => openPage("menu"),
    openInfo: () => openPage("info"),
    openChart,
  };
}
