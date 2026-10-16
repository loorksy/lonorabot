import { Trans, useLingui } from "@lingui/react/macro";
import type { Agent, AttentionPolicy } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useAttention } from "../../providers/AttentionProvider";

export function AttentionCount() {
  const { items } = useAttention();
  return items.length > 0 ? (
    <span className="tpl-unread-badge">
      {items.length}
      {items.length === 50 ? "+" : ""}
    </span>
  ) : null;
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
  const labels = {
    watch_condition_met: t`Watch condition changed`,
    emergency_stop: t`Emergency Stop is active`,
    approval_required: t`Waiting for approval`,
    approval_resolved: t`Request updated`,
    broker_degraded: t`Broker connection needs review`,
    broker_recovered: t`Broker connection recovered`,
    external_broker_activity: t`Broker account changed`,
    setup_confirmed: t`Watch confirmed — review current evidence`,
    thesis_invalidated: t`Setup validity changed`,
    goal_changed: t`Trading goal updated`,
    collaboration_completed: t`Collaboration result is ready`,
    task_review: t`Task needs review`,
    super_bot_authorization: t`Super Bot needs device authorization`,
    super_bot_changed: t`Super Bot authority updated`,
    task_completed: t`Task completed`,
    internal_update: t`Activity updated`,
  };
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
            {item.parameters.symbol && <bdi>{item.parameters.symbol}</bdi>}
          </div>
          <Link
            to={
              item.parameters.group_id
                ? `/app/g/${item.parameters.group_id}`
                : `/app/${item.agent_id}`
            }
            onClick={() => {
              void seen(item.id).catch(setError);
            }}
          >
            <Trans>Open conversation</Trans>
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
