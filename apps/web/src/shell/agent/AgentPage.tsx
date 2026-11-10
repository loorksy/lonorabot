import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { PermissionState, SupervisionView, TradingReadiness } from "@lonora/contracts";
import { isolate, tradingReadinessLine } from "@lonora/core";
import { Icon, type IconName, PairIcon } from "@lonora/ui-web";
import { type ReactNode, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { useVoice } from "../../hooks/useVoice";
import { useAgentLiveState } from "../../lib/agent-live-state";
import { type Agent, api, type Resource } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { useShellData } from "../data";
import { agentRole } from "../lists/ThreadRow";
import { useNavigation } from "../navigation";
import { SkPage, SkRows } from "../Skeleton";
import { NotFoundPage } from "../StatePage";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import { useAvatarSheet } from "./AvatarSheet";
import {
  accountLabel,
  clockTime,
  hasDelegation,
  isTrader,
  levelIcon,
  levelLabel,
  useRead,
  watchCondition,
} from "./shared";
import "./agent.css";

function NavRow({
  icon,
  label,
  sub,
  onClick,
  lead,
}: {
  icon: IconName;
  label: ReactNode;
  sub?: ReactNode;
  onClick: () => void;
  lead?: ReactNode;
}) {
  return (
    <button type="button" className="row" onClick={onClick}>
      {lead ?? <Icon name={icon} />}
      <span className="body">
        <strong>{label}</strong>
        {sub && <small>{sub}</small>}
      </span>
      <span className="chevron">
        <Icon name="chev" />
      </span>
    </button>
  );
}

/** The reference's modeLine: what the trading agent may do now, from the server's readiness. */
function modeLine(
  readiness: TradingReadiness | null | undefined,
  level: PermissionState["effective_level"],
) {
  if (!readiness) return levelLabel(level);
  switch (readiness.state) {
    case "on_its_own": {
      const p = readiness.params;
      const where =
        p.full_delegation || p.symbol_scope === "account"
          ? t`All pairs`
          : (p.symbols ?? []).map(isolate).join("، ");
      const daily = p.daily_loss;
      const money = daily
        ? t`Daily loss limit ${isolate(daily.currency ? `${daily.amount} ${daily.currency}` : daily.amount)}`
        : t`No money limit`;
      return [levelLabel("autonomous"), where, money].filter(Boolean).join(" · ");
    }
    case "ask_me":
      return t`Ask me on every order`;
    case "no_trading":
      return t`No trading · analysis and follow-up`;
    default:
      // A held state the executor reads (stopped, paused, uncertain, agent paused): the
      // server's own line, never a calmer one.
      return tradingReadinessLine(readiness, i18n.locale);
  }
}

/* «معلومات الوكيل» (route agent): hero, the rows to its pages, trading and safety, watches,
   supervision and the on/off button. Everything is the server's: the level from
   /permissions, the readiness and watches from /state, supervision from /supervision. */
export function AgentPage({ agentId }: { agentId: string }) {
  const data = useShellData();
  const agent = data.agents.find((row) => row.id === agentId);
  if (!agent)
    return data.agentsLoading ? (
      <SkPage>
        <SkRows count={6} />
      </SkPage>
    ) : (
      <NotFoundPage />
    );
  return <AgentPageBody key={agent.id} agent={agent} />;
}

function AgentPageBody({ agent }: { agent: Agent }) {
  const data = useShellData();
  const nav = useNavigation();
  const toast = useToast();
  const sheets = useSheets();
  const { refresh } = useClient();
  const openAvatar = useAvatarSheet();
  const voiceCall = useVoice();
  const trader = isTrader(agent);
  const delegated = hasDelegation(agent);
  const personal = agent.role === "personal";
  const permissions = useRead<PermissionState>(
    delegated ? `/agents/${encodeURIComponent(agent.id)}/permissions` : null,
  );
  const live = useAgentLiveState(agent.id).state;
  const supervision = useRead<SupervisionView>(
    agent.role === "delegated" ? null : `/supervision?agent_id=${encodeURIComponent(agent.id)}`,
  );
  const connections = useRead<Resource[]>("/trading/connections");
  const voice = useRead<{ transport_configured: boolean }>("/voice/status");
  const watches = useRead<Resource[]>(
    trader ? `/watches?agent_id=${encodeURIComponent(agent.id)}` : null,
  );
  const [busy, setBusy] = useState(false);
  const level = permissions.value?.effective_level ?? "analysis";
  const accounts = connections.value ?? [];
  const supervisor = supervision.value?.supervised_by[0]?.supervisor;
  const go = (path: string) => nav.go(path);
  const q = `?agent=${encodeURIComponent(agent.id)}`;

  const call = () => {
    // Q58: no voice provider → the button stays, dimmed; a tap explains and links to it.
    if (voice.value && !voice.value.transport_configured) {
      sheets.open({
        id: "voice-missing",
        title: t`Calls are not set up`,
        body: (
          <>
            <p className="muted">
              <Trans>Calling an agent needs a voice provider. Add one in the voice settings.</Trans>
            </p>
            <button
              type="button"
              className="btn full primary"
              onClick={() => {
                sheets.close();
                nav.go("/app/settings?tab=voice");
              }}
            >
              <Trans>Open voice settings</Trans>
            </button>
          </>
        ),
      });
      return;
    }
    if (voiceCall.target) voiceCall.expand();
    else void voiceCall.start(agent, null);
  };

  const toggle = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.patch(`/agents/${agent.id}`, { paused: !agent.paused });
      data.refresh();
    } catch (failure) {
      // The server refuses some pauses (Lonora, a trading agent's own); its words, in a toast.
      toast(userError(failure), { type: "error" });
    } finally {
      setBusy(false);
    }
  };

  const controlWatch = async (watch: Resource, action: "pause" | "resume" | "cancel") => {
    try {
      await api.post(`/watches/${watch.id}/control`, { action });
      watches.reload();
      refresh();
      if (action === "cancel")
        toast(t`Watch cancelled`, {
          type: "success",
          action: {
            label: t`Undo`,
            run: () =>
              void api
                .post(`/watches/${watch.id}/control`, { action: "resume" })
                .then(() => {
                  watches.reload();
                  refresh();
                })
                .catch((failure) => toast(userError(failure), { type: "error" })),
          },
        });
      else toast(action === "pause" ? t`Watch paused` : t`Watch resumed`, { type: "success" });
    } catch (failure) {
      toast(userError(failure), { type: "error" });
    }
  };

  const shownWatches = (watches.value ?? []).filter(
    (row) => row.payload.enabled !== false || row.state?.code === "watch_paused",
  );

  return (
    <>
      <section className="hero">
        <span className="edit-wrap">
          <AgentAvatar agent={agent} />
          <button
            type="button"
            className="pencil"
            aria-label={t`Edit avatar`}
            onClick={() => openAvatar(agent)}
          >
            <Icon name="edit" />
          </button>
        </span>
        <h2>
          <bdi>{agent.name}</bdi>
        </h2>
        <p>
          <bdi>{agentRole(agent)}</bdi>
        </p>
        {delegated && permissions.value && (
          <span className="badge">
            <Icon name={levelIcon[level]} />
            {levelLabel(level)}
          </span>
        )}
        {supervisor && (
          <button
            type="button"
            className="sup-line"
            onClick={() => go(`/app/agent/${supervisor.id}`)}
          >
            <Icon name="eye" />
            <span>
              <Trans>Supervised by {isolate(supervisor.name ?? "")}</Trans>
            </span>
            <Icon name="chev" />
          </button>
        )}
        <div className="hero-actions">
          <button type="button" onClick={() => go(`/app/${agent.id}`)}>
            <span className="icon">
              <Icon name="chat" />
            </span>
            <Trans>Chat</Trans>
          </button>
          <button
            type="button"
            aria-disabled={voice.value && !voice.value.transport_configured ? true : undefined}
            onClick={call}
          >
            <span className="icon">
              <Icon name="phone" />
            </span>
            <Trans>Call</Trans>
          </button>
        </div>
      </section>
      <div className="group">
        <NavRow
          icon="user"
          label={<Trans>Identity and model</Trans>}
          onClick={() => go(`/app/identity/${agent.id}`)}
        />
        <NavRow
          icon="book"
          label={<Trans>Knowledge</Trans>}
          onClick={() => go(`/app/knowledge${q}`)}
        />
        <NavRow icon="bolt" label={<Trans>Skills</Trans>} onClick={() => go(`/app/skills${q}`)} />
        <NavRow icon="target" label={<Trans>Goals</Trans>} onClick={() => go(`/app/goals${q}`)} />
        <NavRow
          icon="clock"
          label={<Trans>Scheduled tasks</Trans>}
          onClick={() => go(`/app/routines${q}`)}
        />
        <NavRow icon="file" label={<Trans>Files</Trans>} onClick={() => go(`/app/artifacts${q}`)} />
        {(trader || agent.trading_symbol) && (
          <NavRow
            icon="trend"
            label={<Trans>Trades</Trans>}
            onClick={() => go(`/app/trades/${agent.id}`)}
          />
        )}
      </div>
      {trader && (
        <>
          <h3>
            <Trans>Trading and safety</Trans>
          </h3>
          <div className="group">
            {agent.trading_account_id ? (
              <>
                <NavRow
                  icon="shield"
                  label={modeLine(live?.trading_readiness, level)}
                  sub={<Trans>Trading · New trades · Restrictions · Account limits</Trans>}
                  // chat.agent-sheet is the composer's (phase 3): the conversation opens it.
                  onClick={() => go(`/app/${agent.id}?sheet=agent`)}
                />
                {accounts.length > 1 && (
                  <NavRow
                    icon="trend"
                    lead={<PairIcon symbol={agent.trading_symbol ?? ""} />}
                    label={<Trans>Trading account</Trans>}
                    sub={
                      <>
                        <bdi>{accountLabel(accounts, agent.trading_account_id)}</bdi> ·{" "}
                        <span className="ltr">{agent.trading_symbol}</span>
                      </>
                    }
                    onClick={() => go(`/app/identity/${agent.id}`)}
                  />
                )}
              </>
            ) : (
              <NavRow
                icon="eye"
                label={levelLabel("analysis")}
                sub={
                  accounts.length
                    ? t`No trading account chosen · choose an account`
                    : t`No trading account linked · link an account`
                }
                onClick={() =>
                  go(accounts.length ? `/app/identity/${agent.id}` : "/app/settings?tab=trading")
                }
              />
            )}
          </div>
          <h3>
            <Trans>Watches</Trans>
          </h3>
          {shownWatches.length ? (
            <div className="group">
              {shownWatches.map((watch) => {
                const paused = watch.state?.code === "watch_paused";
                const until = watch.payload.expires_at;
                return (
                  <div key={watch.id} className={`row wt-row wt-${paused ? "paused" : "active"}`}>
                    <span className="row-icon">
                      <Icon name={paused ? "pause" : "radar"} />
                    </span>
                    <span className="body">
                      <strong className="ltr-mix">
                        <bdi>{watchCondition(watch.payload)}</bdi>
                      </strong>
                      <small>
                        {typeof until === "string" ? (
                          <Trans>
                            Until <span className="ltr">{clockTime(until)}</span>
                          </Trans>
                        ) : (
                          <Trans>Until you stop it</Trans>
                        )}
                        {paused && <> · {t`Paused for now`}</>}
                      </small>
                      <span className="wt-acts">
                        <button
                          type="button"
                          className="btn sm outline"
                          onClick={() => void controlWatch(watch, paused ? "resume" : "pause")}
                        >
                          {paused ? <Trans>Resume</Trans> : <Trans>Pause for now</Trans>}
                        </button>
                        <button
                          type="button"
                          className="btn sm danger"
                          onClick={() => void controlWatch(watch, "cancel")}
                        >
                          <Trans>Cancel</Trans>
                        </button>
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="pad muted small">
              <Trans>No watches.</Trans>
            </p>
          )}
        </>
      )}
      {agent.role !== "delegated" && (
        <SupervisionSection
          agent={agent}
          view={supervision.value}
          onChange={() => {
            supervision.reload();
            refresh();
          }}
        />
      )}
      <p className="note">
        {delegated
          ? t`Permissions are changed from the chip beside the message field in the chat. Services are linked from Settings → Integrations.`
          : t`Services are linked from Settings → Integrations.`}
      </p>
      {/* Q38: hidden on Lonora's page, with no explanatory line. */}
      {!personal && (
        <button
          type="button"
          className={`btn full ${agent.paused ? "primary" : "danger"}`}
          disabled={busy}
          onClick={() => void toggle()}
        >
          {agent.paused ? <Trans>Turn the agent on</Trans> : <Trans>Stop the agent</Trans>}
        </button>
      )}
    </>
  );
}

/* «يشرف على»: the agents this one supervises, «إزالة», and the picker sheet. A grant is
   never money authority (docs/supervision.md). */
function SupervisionSection({
  agent,
  view,
  onChange,
}: {
  agent: Agent;
  view: SupervisionView | undefined;
  onChange: () => void;
}) {
  const data = useShellData();
  const sheets = useSheets();
  const toast = useToast();
  if (!view) return null;
  const supervised = new Set(view.supervises.map((grant) => grant.supervised.id));
  const candidates = data.agents.filter(
    (row) => row.id !== agent.id && row.role !== "delegated" && !supervised.has(row.id),
  );
  const revoke = async (grantId: string) => {
    try {
      await api.post(`/supervision/${grantId}/revoke`, {});
      onChange();
    } catch (failure) {
      toast(userError(failure), { type: "error" });
    }
  };
  const openPicker = () =>
    sheets.open({
      id: "sup",
      title: t`Supervision · ${agent.name}`,
      body: (
        <SupervisionPicker
          agent={agent}
          candidates={candidates}
          onSaved={() => {
            sheets.close();
            onChange();
          }}
        />
      ),
    });
  return (
    <>
      <h3>
        <Trans>Supervises</Trans>
      </h3>
      {view.supervises.length ? (
        <div className="group">
          {view.supervises.map((grant) => {
            const row = data.agents.find((item) => item.id === grant.supervised.id);
            return (
              <div className="row" key={grant.id}>
                {row ? (
                  <AgentAvatar agent={row} />
                ) : (
                  <span className="avatar icon-av">
                    <Icon name="bot" />
                  </span>
                )}
                <span className="body">
                  <strong>
                    <bdi>{grant.supervised.name ?? row?.name ?? ""}</bdi>
                  </strong>
                  <small>
                    <bdi>{row ? agentRole(row) : ""}</bdi>
                  </small>
                </span>
                <button
                  type="button"
                  className="btn sm outline"
                  onClick={() => void revoke(grant.id)}
                >
                  <Trans>Remove</Trans>
                </button>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="pad muted small">
          <Trans>It does not supervise any agent now.</Trans>
        </p>
      )}
      {candidates.length > 0 && (
        <button type="button" className="btn full outline" onClick={openPicker}>
          <Trans>Add agents to supervise</Trans>
        </button>
      )}
    </>
  );
}

function SupervisionPicker({
  agent,
  candidates,
  onSaved,
}: {
  agent: Agent;
  candidates: Agent[];
  onSaved: () => void;
}) {
  const toast = useToast();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!picked.size || busy) return;
    setBusy(true);
    try {
      for (const id of picked)
        await api.post("/supervision", { supervisor_id: agent.id, supervised_id: id });
      onSaved();
    } catch (failure) {
      toast(userError(failure), { type: "error" });
      setBusy(false);
    }
  };
  return (
    <>
      <p className="muted">
        <Trans>
          {isolate(agent.name)} follows the work of the chosen agents and answers you about it with
          evidence. This gives it no execution authority.
        </Trans>
      </p>
      <div className="group">
        {candidates.map((row) => {
          const on = picked.has(row.id);
          return (
            // biome-ignore lint/a11y/useSemanticElements: a whole row toggles, as in the reference
            <button
              type="button"
              key={row.id}
              className={`row reach-opt${on ? " on" : ""}`}
              role="checkbox"
              aria-checked={on}
              onClick={() =>
                setPicked((old) => {
                  const next = new Set(old);
                  if (on) next.delete(row.id);
                  else next.add(row.id);
                  return next;
                })
              }
            >
              <AgentAvatar agent={row} />
              <span className="body">
                <strong>
                  <bdi>{row.name}</bdi>
                </strong>
                <small>
                  <bdi>{agentRole(row)}</bdi>
                </small>
              </span>
              <span className={`pick-box${on ? " on" : ""}`} aria-hidden="true">
                {on && <Icon name="check" />}
              </span>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        className={`btn full primary${picked.size ? "" : " is-off"}`}
        disabled={!picked.size || busy}
        onClick={() => void save()}
      >
        <Trans>Add</Trans>
      </button>
    </>
  );
}
