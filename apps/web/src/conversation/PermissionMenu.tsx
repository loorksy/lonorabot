import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentModelSummary, OwnerAction, TradingMode } from "@lonora/contracts";
import { mandateLine, modeChangeLine, ownerActionText } from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { useEffect, useRef, useState } from "react";
import type { Agent } from "../lib/api";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import { usePopover, usePopoverPage } from "../shell/lists/Popover";
import { useNavigation } from "../shell/navigation";
import { useToast } from "../shell/Toast";

/* The trading-mode chip and its menu. The chip is the agent's Mandate: one word for the
   mode, and the menu posts that card's decision. An agent with no connected account has
   no control (Q9). The level is never changed by text, and there is no ladder. */

/** The chip's word for the agent's mode. Null when the server sent no mode: never a guess. */
export function modeWord(mode: string | null | undefined): string | null {
  const words = ownerActionText(i18n.locale);
  if (mode === "full") return words.modeFull;
  if (mode === "ask") return words.modeAsk;
  return null;
}

function modeIcon(mode: string | null | undefined): IconName {
  return mode === "full" ? "alert" : "userCheck";
}

/** The agent's live Mandate card. Reading never raises one. */
export function readMandate(agentId: string): Promise<OwnerAction | null> {
  return api.get<OwnerAction | null>(
    `/owner-actions/mandate?agent_id=${encodeURIComponent(agentId)}`,
  );
}

/** Apply the mode the button showed. Only the Mandate card can set Full. */
export function decideMandate(cardId: string, mode: TradingMode): Promise<OwnerAction> {
  return api.post<OwnerAction>(`/owner-actions/${encodeURIComponent(cardId)}/decision`, {
    decision: "confirm",
    trading_mode: mode,
  });
}

export function PermissionChip({
  agent,
  isGroup,
  trading,
}: {
  threadId?: string;
  agent?: Agent;
  isGroup: boolean;
  trading: boolean;
}) {
  const popover = usePopover();
  const nav = useNavigation();
  if (isGroup)
    return (
      <button
        type="button"
        className="mode-chip"
        onClick={() => window.dispatchEvent(new CustomEvent("lonora:members-permissions"))}
      >
        <Icon name="users" />
        <span>
          <Trans>Members</Trans>
        </span>
        <Icon name="down" />
      </button>
    );
  // No connected account: no mode control (Q9). Nothing here says the agent cannot trade.
  if (!agent || !trading) return null;
  const mode = agent.trading_mode;
  const named = modeWord(mode);
  if (mode !== "ask" && mode !== "full")
    return (
      <span
        className="mode-chip is-off"
        role="status"
        data-testid="permission-chip"
        data-level="unknown"
        data-mode="unknown"
      >
        <Icon name="alert" />
        <span>{t`Trading mode unknown`}</span>
      </span>
    );
  return (
    <button
      type="button"
      className={`mode-chip lvl-${mode === "full" ? "auto" : "ask"}`}
      aria-haspopup="menu"
      aria-expanded="false"
      aria-label={mandateLine(mode, i18n.locale) ?? named ?? ""}
      data-testid="permission-chip"
      data-level={mode}
      data-mode={mode}
      onClick={(event) =>
        popover.open(
          event.currentTarget,
          <PermissionMenu agent={agent} go={nav.go} />,
          t`Trading mode`,
          { cls: "mode-pop", morph: true },
        )
      }
    >
      <Icon name={modeIcon(mode)} />
      <span>{named}</span>
      <Icon name="down" />
    </button>
  );
}

function PermissionMenu({ agent, go }: { agent: Agent; go: (path: string) => void }) {
  const popover = usePopover();
  const toast = useToast();
  const { refresh } = useClient();
  const [page, setPage] = useState<"mode" | "model">("mode");
  const [summary, setSummary] = useState<AgentModelSummary | null>(null);
  const [card, setCard] = useState<OwnerAction | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const modelRow = useRef<HTMLButtonElement>(null);
  const toMode = () => {
    setPage("mode");
    requestAnimationFrame(() => modelRow.current?.focus({ preventScroll: true }));
  };
  usePopoverPage(page !== "mode", toMode);
  const path = `/agents/${encodeURIComponent(agent.id)}`;
  useEffect(() => {
    let live = true;
    void api
      .get<AgentModelSummary>(`${path}/model/summary`)
      .then((row) => live && setSummary(row))
      .catch(() => undefined);
    void readMandate(agent.id)
      .then((row) => live && setCard(row))
      .catch(() => live && setCard(null));
    return () => {
      live = false;
    };
  }, [agent.id, path]);
  const words = ownerActionText(i18n.locale);
  const mode: TradingMode | null =
    agent.trading_mode === "full" || agent.trading_mode === "ask" ? agent.trading_mode : null;
  const other: TradingMode | null = mode === "full" ? "ask" : mode === "ask" ? "full" : null;
  const apply = async (next: TradingMode) => {
    if (!card) return;
    setBusy(true);
    try {
      const updated = await decideMandate(card.id, next);
      const applied = updated.result.trading_mode === "full" ? "full" : "ask";
      popover.close();
      toast(modeChangeLine(agent.name, applied, updated.result.withdrawn ?? 0, i18n.locale), {
        type: "success",
      });
      refresh();
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  const auto = summary ? !summary.record.preference.primary : false;
  const modelValue = auto
    ? t({ message: "Your default model", context: "model" })
    : (summary?.current.name ?? summary?.current.model ?? "—");
  const showCard = async () => {
    setBusy(true);
    try {
      setCard(
        await api.post<OwnerAction>(
          `/owner-actions/mandate?agent_id=${encodeURIComponent(agent.id)}`,
          {},
        ),
      );
      refresh();
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mp-pages" data-page={page === "mode" ? "1" : "2"}>
      <div className="mp-page p1" inert={page !== "mode" ? true : undefined}>
        <div className="pop-title">
          <Trans>Trading mode · {agent.name}</Trans>
        </div>
        {mode && (
          <div className="pop-opt on" data-testid="mode-now">
            <span className="pop-opt-body">
              <strong>
                {words.mandateNow}: {mode === "full" ? words.modeFull : words.modeAsk}
              </strong>
              <small>{mode === "full" ? words.modeFullLine : words.modeAskLine}</small>
            </span>
            <Icon name="check" />
          </div>
        )}
        {other && card && (
          <button
            type="button"
            className="pop-opt"
            role="menuitem"
            data-testid={`mode-option-${other}`}
            disabled={busy}
            onClick={() => void apply(other)}
          >
            <span className="pop-opt-body">
              <strong>{other === "full" ? words.modeFull : words.modeAsk}</strong>
              <small>{other === "full" ? words.modeFullLine : words.modeAskLine}</small>
            </span>
          </button>
        )}
        {other && card === null && (
          <button
            type="button"
            className="pop-opt"
            role="menuitem"
            disabled={busy}
            onClick={() => void showCard()}
          >
            {words.mandateRequest}
          </button>
        )}
        <div className="pop-sep" />
        <button
          ref={modelRow}
          type="button"
          className="pop-row mp-model-row"
          role="menuitem"
          aria-haspopup="menu"
          onClick={() => setPage("model")}
        >
          <span>
            <Trans>Model</Trans>
          </span>
          <span className="pop-val">{modelValue}</span>
          <Icon name="chev" />
        </button>
      </div>
      <div
        className="mp-page p2"
        inert={page === "mode" ? true : undefined}
        aria-hidden={page === "mode"}
      >
        {page === "model" ? (
          <ModelPage
            go={go}
            agent={agent}
            summary={summary}
            onSummary={setSummary}
            onBack={toMode}
          />
        ) : null}
      </div>
    </div>
  );
}

/** The agent settings sheet: the same Mandate card the chip menu posts, or nothing (Q9). */
export function MandateSettings({ agent }: { agent: Agent }) {
  const toast = useToast();
  const { refresh } = useClient();
  const [card, setCard] = useState<OwnerAction | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!agent.trading_account_id) return;
    let live = true;
    void readMandate(agent.id)
      .then((row) => live && setCard(row))
      .catch(() => live && setCard(null));
    return () => {
      live = false;
    };
  }, [agent.id, agent.trading_account_id]);
  if (!agent.trading_account_id) return null;
  const words = ownerActionText(i18n.locale);
  const mode: TradingMode | null =
    agent.trading_mode === "full" || agent.trading_mode === "ask" ? agent.trading_mode : null;
  const other: TradingMode | null = mode === "full" ? "ask" : mode === "ask" ? "full" : null;
  const apply = async (next: TradingMode) => {
    if (!card) return;
    setBusy(true);
    try {
      const updated = await decideMandate(card.id, next);
      const applied = updated.result.trading_mode === "full" ? "full" : "ask";
      toast(modeChangeLine(agent.name, applied, updated.result.withdrawn ?? 0, i18n.locale), {
        type: "success",
      });
      refresh();
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="mandate-settings">
      <h3>
        <Trans>Trading</Trans>
      </h3>
      <p>{mandateLine(mode, i18n.locale)}</p>
      {mode && <p>{mode === "full" ? words.modeFullLine : words.modeAskLine}</p>}
      {other && card ? (
        <button type="button" disabled={busy} onClick={() => void apply(other)}>
          {other === "full" ? words.modeFull : words.modeAsk}
        </button>
      ) : card === null ? (
        <p>
          <Trans>This agent has no Mandate card yet.</Trans>
        </p>
      ) : null}
    </section>
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
  const auto = summary ? !summary.record.preference.primary : false;
  const current = summary?.current;
  const choose = async (choice: { provider: string; model: string } | null) => {
    try {
      await api.put(path, {
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
  const models = summary?.available ?? [];
  return (
    <>
      <div className="mp-head">
        <button
          type="button"
          className="icon mp-back"
          aria-label={t`Back to the trading mode`}
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
          <strong>{t({ message: "Your default model", context: "model" })}</strong>
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
