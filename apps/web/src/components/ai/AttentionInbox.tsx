import { Trans, useLingui } from "@lingui/react/macro";
import type { Agent, AttentionCode, AttentionPolicy } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useAttention } from "../../providers/AttentionProvider";
import { recoveryPath } from "../../shell/routes";

/** What each attention item says (the inbox and the heads-up banner). */
export function useAttentionLabels(): Record<AttentionCode, string> {
  const { t } = useLingui();
  return {
    watch_condition_met: t`Watch condition changed`,
    approval_required: t`Waiting for approval`,
    approval_resolved: t`Request updated`,
    broker_degraded: t`Broker connection needs review`,
    broker_recovered: t`Broker connection recovered`,
    external_broker_activity: t`Broker account changed`,
    setup_confirmed: t`Watch confirmed — review current evidence`,
    thesis_invalidated: t`Setup validity changed`,
    collaboration_completed: t`Collaboration result is ready`,
    task_review: t`Task needs review`,
    task_degraded: t`Task is retrying through a model outage`,
    // Retired Super Bot items still stored in the inbox; nothing raises them any more.
    super_bot_authorization: t`Request updated`,
    super_bot_changed: t`Request updated`,
    task_completed: t`Task completed`,
    internal_update: t`Activity updated`,
    maintenance_item_quarantined: t`A background item was paused after repeated errors; everything else keeps running`,
    run_quarantined: t`Work stopped after repeated interruptions`,
    operation_unresolved: t`A trade still has no confirmed broker result`,
    operation_uncertain: t`The broker did not confirm a trade — tell Lonora whether it executed`,
    gateway_degraded: t`Background service is running late`,
    agent_notification: t`Your agent alerted you`,
  };
}
export function AttentionInbox({
  agents,
  compact = false,
}: {
  agents: Agent[];
  compact?: boolean;
}) {
  const { t, i18n } = useLingui();
  const { items, error: fetchError, seen } = useAttention();
  const [settings, setSettings] = useState<AttentionPolicy>();
  const [error, setError] = useState<unknown>();
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (compact) return;
    let active = true;
    void api
      .get<AttentionPolicy>("/attention/policy")
      .then((value) => {
        if (active) setSettings(value);
      })
      .catch((cause) => {
        if (active) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [compact]);
  const labels = useAttentionLabels();
  if (compact && !items.length) return null;
  return (
    <section aria-label={t`Notifications`} data-testid="attention-inbox">
      <h2>
        <Trans>Notifications</Trans>
      </h2>
      {error != null || fetchError != null ? (
        <p role="alert">{userError(error ?? fetchError)}</p>
      ) : null}
      {!compact && settings && (
        <label className="check">
          <input
            type="checkbox"
            role="switch"
            data-lonora-switch="true"
            aria-checked={settings.opportunities}
            checked={settings.opportunities}
            disabled={saving}
            onChange={async (event) => {
              setSaving(true);
              try {
                setSettings(
                  await api.put<AttentionPolicy>("/attention/policy", {
                    ...settings,
                    opportunities: event.target.checked,
                    locale: i18n.locale === "ar" ? "ar" : "en",
                  }),
                );
              } catch (cause) {
                setError(cause);
              } finally {
                setSaving(false);
              }
            }}
          />
          <Trans>Notify me about confirmed opportunities</Trans>
        </label>
      )}
      {!items.length && !compact && (
        <p className="muted">
          <Trans>No new notifications</Trans>
        </p>
      )}
      {(compact ? items.slice(0, 3) : items).map((item) => (
        <article key={item.id} className="tpl-activity-run" data-attention-id={item.id}>
          <div>
            <p>{labels[item.code]}</p>
            <p dir="auto">{agents.find((agent) => agent.id === item.agent_id)?.name}</p>
            {item.code === "agent_notification" && item.parameters.summary && (
              <p dir="auto" data-testid="attention-summary">
                {item.parameters.summary}
              </p>
            )}
            {item.parameters.symbol && <bdi>{item.parameters.symbol}</bdi>}
          </div>
          <Link
            to={
              item.code === "broker_degraded"
                ? recoveryPath(item.parameters.account_id)
                : item.parameters.group_id
                  ? `/app/g/${item.parameters.group_id}`
                  : `/app/${item.agent_id}`
            }
            onClick={() => {
              void seen(item.id).catch(setError);
            }}
          >
            {item.code === "broker_degraded" ? (
              <Trans>Outage and recovery</Trans>
            ) : (
              <Trans>Open conversation</Trans>
            )}
          </Link>
          <button
            type="button"
            onClick={() => {
              void seen(item.id).catch(setError);
            }}
          >
            <Trans>Mark as read</Trans>
          </button>
        </article>
      ))}
    </section>
  );
}
