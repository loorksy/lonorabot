import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { showsTradingControl } from "@lonora/core";
import { useCallback, useEffect, useRef } from "react";
import { useChatPrefs } from "../conversation/prefs";
import { useAgentSheet } from "../conversation/sheets/AgentSheet";
import { useWatchesSheet } from "../conversation/sheets/WatchesSheet";
import type { Agent, Resource } from "../lib/api";
import { AgentSettings } from "../pages/shell/bot-settings";
import { useChartSheet } from "./agent/ChartSheet";
import { PopItem, PopSep, usePopover } from "./lists/Popover";
import { useLists } from "./lists/state";
import { useNavigation } from "./navigation";
import { useSheets } from "./sheets/SheetHost";

/* The conversation's ⋮ menu (reference chat-menu): a popover beside the button, in the
   reference's order. Its info item goes to the agent or group page; «مسح المحادثة» hides the
   history for the owner (Q1): nothing is deleted. */
export function useChatMenu({
  agent,
  group,
  memberAgents,
  threadId,
  liveTasks,
}: {
  agent?: Agent;
  group?: Resource;
  memberAgents: Agent[];
  threadId?: string;
  /** The agent's open tasks: one that may need the owner shows «الحالة والأمان». */
  liveTasks: number;
}) {
  const sheets = useSheets();
  const popover = usePopover();
  const nav = useNavigation();
  const lists = useLists();
  const prefs = useChatPrefs();
  const statusSheet = useAgentSheet((id) =>
    window.dispatchEvent(new CustomEvent("lonora:jump", { detail: { id } })),
  );
  const watchesSheet = useWatchesSheet(nav.go);
  // Lonora (the personal agent) trades too (Q19): its chat has the capsule and the sheet's
  // trading section like any trading agent's.
  const trading = Boolean(
    agent &&
      (agent.template === "trading" ||
        showsTradingControl({ role: agent.role, trading_account_id: agent.trading_account_id })),
  );
  // The chart sheet (chart.sheet, Q37): the agent's pair, or the chart an answer named.
  const chartSheet = useChartSheet();
  const openChart = useCallback(
    (chartId?: string) =>
      chartSheet(
        agent?.trading_account_id && agent.trading_symbol
          ? { accountId: agent.trading_account_id, symbol: agent.trading_symbol }
          : null,
        {
          agentId: agent?.id,
          chartId,
          threadId: group?.state?.thread_id ? String(group.state.thread_id) : undefined,
        },
      ),
    [chartSheet, agent, group],
  );
  const openInfo = useCallback(() => {
    if (agent) nav.go(`/app/agent/${agent.id}`);
    else if (group) nav.go(`/app/group/${group.id}`);
  }, [nav, agent, group]);
  // The header's avatar and name open the agent's settings sheet, as before (its market, model,
  // supervision and full permission panel), until phase 3 removes it; a group's open its page.
  const openSettings = useCallback(() => {
    if (!agent) return openInfo();
    const title = t`Agent info`;
    sheets.open({
      id: "agent-settings",
      bar: true,
      title,
      label: title,
      body: (
        <div className="legacy-surface">
          <AgentSettings key={agent.id} agent={agent} onClose={() => sheets.close()} />
        </div>
      ),
    });
  }, [sheets, agent, openInfo]);
  const confirmClear = useCallback(() => {
    const row = lists.rows.find(
      (item) => item.key === (agent ? `agent:${agent.id}` : `group:${group?.id}`),
    );
    const title = t`Clear the chat`;
    sheets.open({
      id: "clear-chat",
      title,
      label: title,
      body: (
        <>
          <p>
            {group ? (
              <Trans>
                This chat's messages are hidden for you. The group stays with its members.
              </Trans>
            ) : (
              <Trans>This chat's messages are hidden for you. The agent and its record stay.</Trans>
            )}
          </p>
          <div className="actions">
            <button type="button" className="btn outline" onClick={() => sheets.close()}>
              <Trans>Cancel</Trans>
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={() => {
                sheets.close(true);
                if (!row || !threadId) return;
                lists
                  .clear([{ ...row, threadId }])
                  .then(
                    () =>
                      window.dispatchEvent(
                        new CustomEvent("lonora:chat-cleared", { detail: { threadId } }),
                      ),
                    lists.failed,
                  );
              }}
            >
              <Trans>Clear</Trans>
            </button>
          </div>
        </>
      ),
    });
  }, [sheets, lists, agent, group, threadId]);
  // A tap on ⋮ before the agent or group has loaded opens the menu once it arrives.
  const waiting = useRef<HTMLElement | null>(null);
  const openMenu = useCallback(
    (anchor: HTMLElement) => {
      if (!agent && !group) {
        waiting.current = anchor;
        return;
      }
      const taskAgent =
        agent?.id ??
        (typeof group?.payload.lead_agent_id === "string" ? group.payload.lead_agent_id : null) ??
        memberAgents[0]?.id;
      // A sheet opened from the menu gives focus back to ⋮ when it closes.
      const fromAnchor = (open: () => void) => () => {
        anchor.focus({ preventScroll: true });
        open();
      };
      popover.open(
        anchor,
        <>
          <PopItem
            icon={group ? "users" : "info"}
            label={group ? <Trans>Group info</Trans> : <Trans>Agent info</Trans>}
            onSelect={openInfo}
          />
          {(group || trading || agent?.trading_symbol) && (
            <PopItem
              icon="chart"
              label={<Trans>Chart</Trans>}
              onSelect={fromAnchor(() => openChart())}
            />
          )}
          {agent && (trading || prefs.agentStatus || liveTasks > 0) && (
            <PopItem
              icon="shield"
              label={<Trans>Status and safety</Trans>}
              onSelect={fromAnchor(() => statusSheet(agent, trading, prefs.agentStatus))}
            />
          )}
          {agent && trading && agent.trading_account_id && (
            <PopItem
              icon="radar"
              label={<Trans>Watches</Trans>}
              onSelect={fromAnchor(() => watchesSheet(agent))}
            />
          )}
          <PopItem
            icon="task"
            label={<Trans>New task</Trans>}
            onSelect={() => nav.go(`/app/new-task${taskAgent ? `?agent=${taskAgent}` : ""}`)}
          />
          {agent && (
            <PopItem
              icon="file"
              label={<Trans>Agent files</Trans>}
              onSelect={() => nav.go(`/app/artifacts?agent=${agent.id}`)}
            />
          )}
          <PopSep />
          <PopItem
            icon="trash"
            danger
            label={<Trans>Clear the chat</Trans>}
            onSelect={fromAnchor(confirmClear)}
          />
        </>,
        t`Chat menu`,
      );
    },
    [
      popover,
      nav,
      agent,
      group,
      memberAgents,
      trading,
      prefs.agentStatus,
      liveTasks,
      openInfo,
      openChart,
      statusSheet,
      watchesSheet,
      confirmClear,
    ],
  );
  useEffect(() => {
    const anchor = waiting.current;
    if (!anchor || (!agent && !group)) return;
    waiting.current = null;
    if (anchor.isConnected) openMenu(anchor);
  }, [openMenu, agent, group]);
  return { openMenu, openInfo, openSettings, openChart, confirmClear };
}
