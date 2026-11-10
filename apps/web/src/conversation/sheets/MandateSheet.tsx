import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type {
  AccountAuthorityDraft,
  AccountAuthorityDraftResult,
  AuthorityAction,
  AuthorityDuration,
  OwnerAction,
  PermissionState,
} from "@lonora/contracts";
import { Icon } from "@lonora/ui-web";
import { useCallback, useState } from "react";
import { OwnerActionCard } from "../../components/owner-actions/OwnerActionCard";
import { AgentPermissions } from "../../components/permissions/AgentPermissions";
import type { Agent } from "../../lib/api";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useSheets } from "../../shell/sheets/SheetHost";

/* «التفويض» (reference OA_R.grant_authority, Desktop-37 7774-7799): مخصّص / كامل, the
   markets, the allowed actions, the duration, the daily loss (D1: 3% suggested), own
   positions. «التوقيع بمفتاح المرور» drafts the grant on the server
   (POST /agents/{id}/account-authorities/draft, Q17/Q18); the drafted grant card then opens in
   the same sheet, where the passkey signs exactly what the server stored. Nothing is active
   before that signature; the money-limit choice («التشغيل دون حد مالي») and a conflicting
   agent's stop are the card's own switches. */

type Kind = "open" | "modify" | "close";
const ACTIONS: Record<Kind, AuthorityAction[]> = {
  open: ["buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop"],
  modify: ["modify_position", "modify_order"],
  close: ["close_position", "cancel_order"],
};
const actionLabel = (kind: Kind) =>
  ({
    open: t`Open new trades`,
    modify: t`Modify the stop and target`,
    close: t`Close trades`,
  })[kind];
const durationLabel = (d: AuthorityDuration) =>
  ({
    "12h": t`12 hours`,
    "24h": t`24 hours`,
    "7d": t`7 days`,
    until_stopped: t`Until cancelled`,
  })[d];

function MandateBody({ agent, threadId }: { agent: Agent; threadId?: string }) {
  const [mode, setMode] = useState<"custom" | "full">("custom");
  const [allPairs, setAllPairs] = useState(false);
  const [kinds, setKinds] = useState<Kind[]>(["open", "modify", "close"]);
  const [duration, setDuration] = useState<AuthorityDuration>("24h");
  const [loss, setLoss] = useState(3);
  const [manual, setManual] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [card, setCard] = useState<OwnerAction | null>(null);
  if (card) return <OwnerActionCard row={card} onChanged={setCard} inSheet />;
  const full = mode === "full";
  const symbol = agent.trading_symbol;
  const draft = async () => {
    if (!full && !kinds.length) return setError(new Error(t`Choose at least one action`));
    setBusy(true);
    setError(undefined);
    const body: AccountAuthorityDraft = full
      ? { mode: "full", ...(threadId ? { thread_id: threadId } : {}) }
      : {
          mode: "custom",
          ...(threadId ? { thread_id: threadId } : {}),
          ...(allPairs ? { all_pairs: true } : symbol ? { symbols: [symbol] } : {}),
          actions: kinds.flatMap((kind) => ACTIONS[kind]),
          duration,
          allow_manual_positions: manual,
          daily_loss_percent: String(loss),
        };
    try {
      const result = await api.post<AccountAuthorityDraftResult>(
        `/agents/${encodeURIComponent(agent.id)}/account-authorities/draft`,
        body,
      );
      setCard(result.owner_action);
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="oa in-sheet act-grant_authority st-pending">
      {/* biome-ignore lint/a11y/useSemanticElements: the reference's radio rows */}
      <div className="oa-radios" role="radiogroup" aria-label={t`Kind of mandate`}>
        {(["custom", "full"] as const).map((value) => (
          // biome-ignore lint/a11y/useSemanticElements: the reference's radio rows
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={mode === value}
            className={`oa-radio${mode === value ? " on" : ""}`}
            onClick={() => setMode(value)}
          >
            <span>
              <strong>{value === "custom" ? t`Custom mandate` : t`Full mandate`}</strong>
              <small>
                {value === "custom"
                  ? t`You set the markets, actions, duration and money limit`
                  : t`All pairs and all actions until cancelled; the account's limits still apply`}
              </small>
            </span>
            {mode === value && <Icon name="check" />}
          </button>
        ))}
      </div>
      {!full && (
        <div className="oa-fields">
          <div className="oa-f col">
            <span className="oa-l">
              <Trans>Markets</Trans>
            </span>
            {/* biome-ignore lint/a11y/useSemanticElements: the reference's segmented choice */}
            <div className="oa-seg" role="radiogroup">
              {symbol && (
                // biome-ignore lint/a11y/useSemanticElements: the reference's segmented choice
                <button
                  type="button"
                  role="radio"
                  aria-checked={!allPairs}
                  className={!allPairs ? "on" : ""}
                  onClick={() => setAllPairs(false)}
                >
                  <span className="ltr">{symbol}</span>
                </button>
              )}
              {/* biome-ignore lint/a11y/useSemanticElements: the reference's segmented choice */}
              <button
                type="button"
                role="radio"
                aria-checked={allPairs || !symbol}
                className={allPairs || !symbol ? "on" : ""}
                onClick={() => setAllPairs(true)}
              >
                <Trans>All pairs on the account</Trans>
              </button>
            </div>
          </div>
          <div className="oa-f col">
            <span className="oa-l">
              <Trans>Allowed actions</Trans>
            </span>
            {/* biome-ignore lint/a11y/useSemanticElements: the reference's check rows */}
            <div className="oa-checks" role="group">
              {(["open", "modify", "close"] as const).map((kind) => {
                const on = kinds.includes(kind);
                return (
                  // biome-ignore lint/a11y/useSemanticElements: the reference's check rows
                  <button
                    key={kind}
                    type="button"
                    className="oa-check"
                    role="checkbox"
                    aria-checked={on}
                    onClick={() =>
                      setKinds((old) => (on ? old.filter((k) => k !== kind) : [...old, kind]))
                    }
                  >
                    <span className={`pick-box${on ? " on" : ""}`} aria-hidden="true">
                      {on && <Icon name="check" />}
                    </span>
                    <span>{actionLabel(kind)}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="oa-f col">
            <span className="oa-l">
              <Trans>Duration</Trans>
            </span>
            {/* biome-ignore lint/a11y/useSemanticElements: the reference's segmented choice */}
            <div className="oa-seg" role="radiogroup">
              {(["12h", "24h", "7d", "until_stopped"] as const).map((value) => (
                // biome-ignore lint/a11y/useSemanticElements: the reference's segmented choice
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={duration === value}
                  className={duration === value ? "on" : ""}
                  onClick={() => setDuration(value)}
                >
                  {durationLabel(value)}
                </button>
              ))}
            </div>
          </div>
          <div className="oa-f">
            <span className="oa-l">
              <Trans>Daily loss limit</Trans>
              <small>
                <Trans>Suggested value 3%</Trans>
              </small>
            </span>
            {/* biome-ignore lint/a11y/useSemanticElements: the reference's stepper */}
            <div className="oa-num" role="group" aria-label={t`Daily loss limit`}>
              <button
                type="button"
                aria-label={t`Decrease`}
                onClick={() => setLoss((v) => Math.max(0.5, +(v - 0.5).toFixed(2)))}
              >
                <Icon name="minus" />
              </button>
              <output className="ltr">{loss}%</output>
              <button
                type="button"
                aria-label={t`Increase`}
                onClick={() => setLoss((v) => Math.min(20, +(v + 0.5).toFixed(2)))}
              >
                <Icon name="plus" />
              </button>
            </div>
          </div>
          <div className="oa-f">
            <span className="oa-l">
              <Trans>Manage manual trades</Trans>
            </span>
            <button
              type="button"
              className="switch"
              role="switch"
              aria-checked={manual}
              aria-label={t`Manage manual trades`}
              onClick={() => setManual((v) => !v)}
            />
          </div>
        </div>
      )}
      {full && (
        <p className="oa-keep">
          <Icon name="shield" />
          <span>
            <Trans>The account's current limits stay in force.</Trans>
          </span>
        </p>
      )}
      {error != null && (
        <p className="oa-warn" role="alert">
          <Icon name="alert" />
          <span>{userError(error)}</span>
        </p>
      )}
      <div className="oa-actions">
        <button
          type="button"
          className={`btn primary${busy ? " is-busy" : ""}`}
          disabled={busy}
          onClick={() => void draft()}
        >
          <Icon name="fingerprint" />
          <span>
            <Trans>Review and sign with the passkey</Trans>
          </span>
        </button>
      </div>
      <p className="note">
        <Trans>
          Nothing becomes active before your passkey signature; the next step shows exactly what you
          sign.
        </Trans>
      </p>
    </div>
  );
}

export function useMandateSheet() {
  const sheets = useSheets();
  return useCallback(
    (agent: Agent, _permission: PermissionState | null, details = false, threadId?: string) => {
      const title = details ? t`Mandate details` : t`Delegated execution`;
      sheets.open({
        id: "mandate",
        bar: true,
        title,
        label: title,
        body: details ? (
          // «تفاصيل التفويض»: the signed grant and «إلغاء التفويض» through the permission flow.
          <div className="legacy-surface">
            <AgentPermissions key={agent.id} agent={agent} threadId="" surface="settings" />
          </div>
        ) : (
          <MandateBody agent={agent} threadId={threadId} />
        ),
      });
    },
    [sheets],
  );
}
