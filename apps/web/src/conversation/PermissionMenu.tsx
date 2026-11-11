import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentModelSummary, AgentPermissionLevel, PermissionState } from "@lonora/contracts";
import { Icon, type IconName } from "@lonora/ui-web";
import { useEffect, useRef, useState } from "react";
import type { Agent } from "../lib/api";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
import { usePopover, usePopoverPage } from "../shell/lists/Popover";
import { useNavigation } from "../shell/navigation";
import { useSheets } from "../shell/sheets/SheetHost";
import { useToast } from "../shell/Toast";
import { useMandateSheet } from "./sheets/MandateSheet";

/* The permission chip and its menu (reference modeChip/modeMenu/modelPage/downgradePage,
   Desktop-37 3821-3827, 3899-3906, 8418-8460). The ladder is trading-only (Q19): a trading
   agent with an account gets the chip; one without an account the dashed «دون تنفيذ» badge
   (→ the no-account sheet); every other agent the «لا يتداول» badge (Q20: a general agent
   researches and answers, it never pays or sends). The level is never changed by text. */

export const LEVEL_ICON: Record<AgentPermissionLevel, IconName> = {
  analysis: "eye",
  supervised: "userCheck",
  autonomous: "bot",
};
export function levelName(level: AgentPermissionLevel) {
  return {
    analysis: t`No execution`,
    supervised: t`Execute with approval`,
    autonomous: t`Delegated execution`,
  }[level];
}
export function levelHint(level: AgentPermissionLevel) {
  return {
    analysis: t`Analyses and follows the market without sending any order.`,
    supervised: t`Every order is shown to you for approval before it is sent.`,
    autonomous: t`Executes within a mandate signed with your passkey and within the account's limits.`,
  }[level];
}

export function PermissionChip({
  agent,
  isGroup,
  trading,
  permission,
  permissionFailed = false,
  onChanged,
  threadId,
}: {
  threadId?: string;
  agent?: Agent;
  isGroup: boolean;
  trading: boolean;
  permission: PermissionState | null;
  permissionFailed?: boolean;
  onChanged: (state: PermissionState) => void;
}) {
  const popover = usePopover();
  const sheets = useSheets();
  const nav = useNavigation();
  if (isGroup)
    return (
      <button
        type="button"
        className="mode-chip"
        aria-haspopup="dialog"
        onClick={() => window.dispatchEvent(new CustomEvent("lonora:members-permissions"))}
      >
        <Icon name="users" />
        <span>
          <Trans>Members</Trans>
        </span>
        <Icon name="down" />
      </button>
    );
  if (!agent) return null;
  if (!trading)
    return (
      <span className="no-trade" role="note" data-testid="permission-no-trading">
        <Icon name="eye" />
        <span>
          <Trans>No trading</Trans>
        </span>
      </span>
    );
  if (!agent.trading_account_id && agent.role !== "personal")
    return (
      <button
        type="button"
        className="no-trade"
        aria-label={t`No execution: no trading account is chosen`}
        onClick={() =>
          sheets.open({
            id: "no-account",
            title: t`No execution`,
            body: (
              <>
                <div className="state-hero">
                  <Icon name="eye" />
                </div>
                <p className="state-lead">
                  <Trans>
                    {agent.name} is not linked to a trading account, so it works without execution:
                    it analyses and follows only.
                  </Trans>
                </p>
                <button
                  type="button"
                  className="btn full primary"
                  onClick={() => {
                    sheets.close();
                    nav.go(`/app/${encodeURIComponent(agent.id)}?settings=trading`);
                  }}
                >
                  <Trans>Choose the trading account</Trans>
                </button>
                <p className="note">
                  <Trans>
                    Then the permission levels appear beside the text field: no execution · execute
                    with approval · delegated execution.
                  </Trans>
                </p>
              </>
            ),
          })
        }
      >
        <Icon name="eye" />
        <span>{levelName("analysis")}</span>
      </button>
    );
  // Until the level is read (or when it cannot be), the chip says so: never a guessed level.
  if (!permission)
    return (
      <span
        className="mode-chip is-off"
        role="status"
        data-testid="permission-chip"
        data-level="unknown"
      >
        <Icon name={permissionFailed ? "alert" : "shield"} />
        <span>{permissionFailed ? t`Permission unknown` : "…"}</span>
      </span>
    );
  const level = permission.effective_level;
  return (
    <button
      type="button"
      className={`mode-chip lvl-${level}`}
      aria-haspopup="menu"
      aria-expanded="false"
      aria-label={t`Permissions: ${levelName(level)}`}
      data-testid="permission-chip"
      data-level={level}
      onClick={(event) =>
        popover.open(
          event.currentTarget,
          <PermissionMenu
            agent={agent}
            permission={permission}
            onChanged={onChanged}
            go={nav.go}
            threadId={threadId}
          />,
          t`Permission level`,
          { cls: "mode-pop", morph: true },
        )
      }
    >
      <Icon name={level === "autonomous" ? "alert" : LEVEL_ICON[level]} />
      <span>{levelName(level)}</span>
      <Icon name="down" />
    </button>
  );
}

function PermissionMenu({
  agent,
  permission,
  onChanged,
  go,
  threadId,
}: {
  threadId?: string;
  agent: Agent;
  permission: PermissionState;
  onChanged: (state: PermissionState) => void;
  go: (path: string) => void;
}) {
  const popover = usePopover();
  const toast = useToast();
  const mandate = useMandateSheet();
  const [page, setPage] = useState<
    { kind: "ladder" } | { kind: "model" } | { kind: "down"; level: AgentPermissionLevel }
  >({
    kind: "ladder",
  });
  const [summary, setSummary] = useState<AgentModelSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const modelRow = useRef<HTMLButtonElement>(null);
  const toLadder = () => {
    setPage({ kind: "ladder" });
    requestAnimationFrame(() => modelRow.current?.focus({ preventScroll: true }));
  };
  usePopoverPage(page.kind !== "ladder", toLadder);
  const level = permission.effective_level;
  const path = `/agents/${encodeURIComponent(agent.id)}`;
  useEffect(() => {
    let live = true;
    void api
      .get<AgentModelSummary>(`${path}/model/summary`)
      .then((row) => live && setSummary(row))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [path]);
  const setLevel = async (next: "analysis" | "supervised") => {
    setBusy(true);
    try {
      const latest = await api.get<PermissionState>(`${path}/permissions`);
      const row = await api.put<PermissionState>(`${path}/permissions`, {
        level: next,
        expected_revision: latest.revision,
      });
      onChanged(row);
      popover.close();
      toast(t`Permission: ${levelName(next)}`, { type: "success" });
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  const pick = (next: AgentPermissionLevel) => {
    if (next === level) return popover.close();
    if (next === "autonomous") {
      popover.close();
      mandate(agent, permission, false, threadId);
      return;
    }
    if (level === "autonomous") return setPage({ kind: "down", level: next });
    void setLevel(next);
  };
  const auto = summary?.record.mode === "automatic";
  const modelValue = auto ? t`Automatic` : (summary?.current.name ?? summary?.current.model ?? "—");
  const grant = permission?.active_authorities.length ? permission.active_authorities[0] : null;
  return (
    <div className="mp-pages" data-page={page.kind === "ladder" ? "1" : "2"}>
      <div className="mp-page p1" inert={page.kind !== "ladder" ? true : undefined}>
        <div className="pop-title">
          <Trans>Permission level · {agent.name}</Trans>
        </div>
        {(["analysis", "supervised", "autonomous"] as const).map((row) => (
          <button
            key={row}
            type="button"
            className={`pop-opt${level === row ? " on" : ""}`}
            role="menuitemradio"
            aria-checked={level === row}
            data-testid={`mode-option-${row}`}
            disabled={busy}
            onClick={() => pick(row)}
          >
            <span className="pop-opt-body">
              <strong>{levelName(row)}</strong>
              <small>{levelHint(row)}</small>
            </span>
            {level === row && <Icon name="check" />}
          </button>
        ))}
        <div className="pop-sep" />
        <button
          ref={modelRow}
          type="button"
          className="pop-row mp-model-row"
          role="menuitem"
          aria-haspopup="menu"
          onClick={() => setPage({ kind: "model" })}
        >
          <span>
            <Trans>Model</Trans>
          </span>
          <span className="pop-val">{modelValue}</span>
          <Icon name="chev" />
        </button>
        {grant && (
          <button
            type="button"
            className="pop-row"
            role="menuitem"
            onClick={() => {
              popover.close();
              mandate(agent, permission, true, threadId);
            }}
          >
            <span>
              <Trans>Mandate details</Trans>
            </span>
            <Icon name="chev" />
          </button>
        )}
        <p className="pop-note">
          <Trans>Closing and tightening the stop loss are always allowed.</Trans>
        </p>
      </div>
      <div
        className="mp-page p2"
        inert={page.kind === "ladder" ? true : undefined}
        aria-hidden={page.kind === "ladder"}
      >
        {page.kind === "down" ? (
          <>
            <div className="mp-head">
              <button
                type="button"
                className="icon mp-back"
                aria-label={t`Back`}
                onClick={toLadder}
              >
                <Icon name="back" />
              </button>
              <strong>
                <Trans>Change the permission level</Trans>
              </strong>
            </div>
            <div className="mp-warn" data-testid="mode-downgrade">
              <span className="mp-warn-ic">
                <Icon name="alert" />
              </span>
              <p>
                <Trans>
                  The signed mandate is revoked; going back to it needs a new signature.
                </Trans>
              </p>
              <div className="mp-ladder">
                <span>{levelName("autonomous")}</span>
                <Icon name="chev" />
                <strong>{levelName(page.level)}</strong>
              </div>
            </div>
            <button
              type="button"
              className="pop-opt danger-opt"
              role="menuitem"
              data-testid="mode-downgrade-confirm"
              disabled={busy}
              onClick={() => void setLevel(page.level as "analysis" | "supervised")}
            >
              <span className="pop-opt-body">
                <strong>
                  <Trans>Confirm: {levelName(page.level)}</Trans>
                </strong>
                <small>
                  {page.level === "analysis"
                    ? t`It stops executing and only analyses and follows`
                    : t`Every order is shown to you for approval before it is sent`}
                </small>
              </span>
            </button>
            <button type="button" className="pop-opt" role="menuitem" onClick={toLadder}>
              <span className="pop-opt-body">
                <strong>
                  <Trans>Keep «{levelName("autonomous")}»</Trans>
                </strong>
                <small>
                  <Trans>No change</Trans>
                </small>
              </span>
            </button>
          </>
        ) : page.kind === "model" ? (
          <ModelPage
            go={go}
            agent={agent}
            summary={summary}
            onSummary={setSummary}
            onBack={toLadder}
          />
        ) : null}
      </div>
    </div>
  );
}

function ModelPage({
  agent,
  summary,
  onSummary,
  onBack,
  go,
}: {
  agent: Agent;
  summary: AgentModelSummary | null;
  onSummary: (row: AgentModelSummary) => void;
  onBack: () => void;
  go: (path: string) => void;
}) {
  const popover = usePopover();
  const toast = useToast();
  const path = `/agents/${encodeURIComponent(agent.id)}/model`;
  const auto = summary?.record.mode === "automatic";
  const current = summary?.current;
  const choose = async (choice: { provider: string; model: string } | null) => {
    try {
      await api.put(path, {
        mode: choice ? "fixed" : "automatic",
        primary: choice ?? null,
        expected_revision: summary?.record.revision,
      });
      const next = await api.get<AgentModelSummary>(`${path}/summary`);
      onSummary(next);
      // the check lands, then back to page 1
      setTimeout(onBack, 220);
    } catch (error) {
      toast(userError(error), { type: "error" });
    }
  };
  const models = summary?.allowed.length ? summary.allowed : (summary?.available ?? []);
  return (
    <>
      <div className="mp-head">
        <button
          type="button"
          className="icon mp-back"
          aria-label={t`Back to the permissions`}
          onClick={onBack}
        >
          <Icon name="back" />
        </button>
        <strong>
          <Trans>Model</Trans>
        </strong>
      </div>
      <button
        type="button"
        className={`pop-opt${auto ? " on" : ""}`}
        role="menuitemradio"
        aria-checked={auto}
        onClick={() => void choose(null)}
      >
        <span className="pop-opt-body">
          <strong>
            <Trans>Automatic</Trans>
          </strong>
          <small>
            {auto && current?.name
              ? t`Running on «${current.name}» now · the routing picks the best fit for each task`
              : t`The routing picks the best fit for each task`}
          </small>
        </span>
        {auto && <Icon name="check" />}
      </button>
      {models.map((row) => {
        const on = !auto && current?.model === row.model && current?.provider === row.provider;
        return (
          <button
            key={`${row.provider}:${row.model}`}
            type="button"
            className={`pop-opt${on ? " on" : ""}`}
            role="menuitemradio"
            aria-checked={on}
            onClick={() =>
              row.provider && row.model && void choose({ provider: row.provider, model: row.model })
            }
          >
            <span className="pop-opt-body">
              <strong className="ltr">{row.name ?? row.model}</strong>
              <small className="ltr">{row.provider}</small>
            </span>
            {on && <Icon name="check" />}
          </button>
        );
      })}
      {summary && (
        <>
          <div className="pop-title">
            <Trans>
              Usage of {agent.name} · last {summary.usage.days} days
            </Trans>
          </div>
          <p className="mp-tot">
            <Trans>{summary.usage.requests} requests · no cap for this agent</Trans>
          </p>
        </>
      )}
      <div className="pop-sep" />
      <button
        type="button"
        className="pop-row"
        role="menuitem"
        onClick={() => {
          popover.close();
          go("/app/settings?tab=models");
        }}
      >
        <Icon name="plus" />
        <span className="mp-grow">
          <Trans>Connect a model provider</Trans>
        </span>
      </button>
    </>
  );
}
