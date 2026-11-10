import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentDeliveryRules, IncomingCallPolicy } from "@lonora/contracts";
import { Icon, type IconName } from "@lonora/ui-web";
import { useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { NotFoundPage } from "../StatePage";
import { useToast } from "../Toast";
import { NOTIFY_DEFAULTS, type NotifyPrefs, useDevicePref } from "./device-prefs";
import { type OwnerProfile, useOwnerProfile } from "./owner";
import { NavRow, Note, ToggleRow, useLoad } from "./ui";

type Channel = IncomingCallPolicy["channel"];
/** The reference's REACH (8368), one to one with the server's ReachMe. */
export const reachOptions = (): [Channel, string, string, IconName][] => [
  ["activity", t`Activity log only`, t`Recorded in Updates without any alert`, "updates"],
  ["notify", t`Notification`, t`An alert on your device`, "bell"],
  ["message", t`Message`, t`A message in the agent's conversation with an alert`, "chat"],
  ["call", t`Call`, t`For urgent matters: the agent calls you`, "phone"],
];
export const reachLabel = (channel: Channel) =>
  reachOptions().find(([value]) => value === channel)?.[1] ?? "";

const clock = (minute: number | null | undefined) =>
  minute == null
    ? ""
    : `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
const minutes = (value: string) => {
  const [hour, minute] = value.split(":").map(Number);
  return Number.isInteger(hour) && Number.isInteger(minute) ? hour * 60 + minute : null;
};

/* «الإشعارات والتواصل» (notifyPage 6158-6166, reachSection/deviceSection 8369-8378): how agents
   reach the owner (one choice), the in-app banner on this device, quiet hours to the minute
   (Q47, in ONE place), the device a call rings, and each agent's own rules. No browser
   notification row until a push channel exists (Q10); Lonora is the only channel (Q53). */
export function NotifyPage() {
  const data = useShellData();
  const toast = useToast();
  const [profile, setProfile] = useOwnerProfile();
  const [prefs, setPrefs] = useDevicePref<NotifyPrefs>("notify", NOTIFY_DEFAULTS);
  const rules = useLoad(
    () => api.get<Record<string, AgentDeliveryRules>>("/agents/notifications"),
    [],
  );
  const attention = useLoad(
    () =>
      api.get<{ opportunities: boolean; informational: boolean; locale: "ar" | "en" }>(
        "/attention/policy",
      ),
    [],
  );
  const [busy, setBusy] = useState(false);
  const policy = profile?.reach_me;
  const save = async (patch: Partial<IncomingCallPolicy>) => {
    if (!policy || busy) return;
    setBusy(true);
    const { enabled: _enabled, ...current } = policy;
    try {
      setProfile(
        await api.put<OwnerProfile>("/owner/preferences", { reach_me: { ...current, ...patch } }),
      );
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  const quiet = policy?.quiet_start_minute != null && policy.quiet_end_minute != null;
  const setWindow = (start: number | null, end: number | null) => {
    if (start != null && start === end)
      return toast(t`Quiet hours must start and end at different times.`, { type: "warn" });
    return save({
      quiet_start_minute: start,
      quiet_end_minute: end,
      quiet_start_hour: start == null ? null : Math.floor(start / 60),
      quiet_end_hour: end == null ? null : Math.floor(end / 60),
    });
  };
  return (
    <>
      <h3>
        <Trans>How to reach you</Trans>
      </h3>
      <div className="group" role="radiogroup" aria-label={t`How to reach you`}>
        {reachOptions().map(([value, title, sub, icon]) => {
          const on = policy?.channel === value;
          return (
            // biome-ignore lint/a11y/useSemanticElements: the reference's own role on its row
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={on}
              disabled={!policy || busy}
              className={`row reach-opt${on ? " on" : ""}`}
              onClick={() =>
                save(
                  value === "call" && !policy?.device_id && profile?.devices[0]
                    ? { channel: value, device_id: profile.devices[0].id }
                    : { channel: value },
                )
              }
            >
              <span className="row-icon">
                <Icon name={icon} />
              </span>
              <span className="body">
                <strong>{title}</strong>
                <small>{sub}</small>
              </span>
              {on && (
                <span className="reach-check">
                  <Icon name="check" />
                </span>
              )}
            </button>
          );
        })}
      </div>
      <h3>
        <Trans>Notifications</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`In-app notifications`}
          sub={t`A bar at the top of the screen when a reply arrives in another conversation`}
          on={prefs.inApp}
          icon="bell"
          onChange={(inApp) => setPrefs({ inApp })}
        />
        <ToggleRow
          title={t`Text preview`}
          sub={t`Show the start of the message in the notification`}
          on={prefs.preview}
          icon="eye"
          onChange={(preview) => setPrefs({ preview })}
        />
        {attention.value && (
          <ToggleRow
            title={t`Notify me about confirmed opportunities`}
            sub={t`An alert when an agent confirms an opportunity`}
            on={attention.value.opportunities}
            icon="target"
            onChange={async (opportunities) => {
              const current = attention.value;
              if (!current) return;
              try {
                attention.set(
                  await api.put("/attention/policy", {
                    ...current,
                    opportunities,
                    locale: i18n.locale === "ar" ? "ar" : "en",
                  }),
                );
              } catch (error) {
                toast(userError(error), { type: "error" });
              }
            }}
          />
        )}
        <ToggleRow
          title={t`Sounds`}
          sub={t`A short tone when a reply arrives`}
          on={prefs.sound}
          icon="volume"
          onChange={(sound) => setPrefs({ sound })}
        />
      </div>
      <h3>
        <Trans>Quiet hours</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`Mute notifications at night`}
          sub={
            quiet
              ? t`From ${clock(policy?.quiet_start_minute)} to ${clock(policy?.quiet_end_minute)}`
              : t`From 22:00 to 08:00`
          }
          on={quiet}
          icon="moon"
          disabled={!policy || busy}
          onChange={(on) => (on ? setWindow(22 * 60, 8 * 60) : setWindow(null, null))}
        />
        {quiet && policy && (
          <>
            <div className="row reach-times">
              <label>
                <span>
                  <Trans>From</Trans>
                </span>
                <input
                  type="time"
                  value={clock(policy.quiet_start_minute)}
                  onChange={(event) => {
                    const start = minutes(event.target.value);
                    if (start != null) void setWindow(start, policy.quiet_end_minute);
                  }}
                />
              </label>
              <label>
                <span>
                  <Trans>To</Trans>
                </span>
                <input
                  type="time"
                  value={clock(policy.quiet_end_minute)}
                  onChange={(event) => {
                    const end = minutes(event.target.value);
                    if (end != null) void setWindow(policy.quiet_start_minute, end);
                  }}
                />
              </label>
            </div>
            <div className="row">
              <span className="row-icon">
                <Icon name="alert" />
              </span>
              <span className="body">
                <strong>
                  <Trans>Urgent always arrives</Trans>
                </strong>
                <small>
                  <Trans>An unconfirmed operation or a restriction on your account</Trans>
                </small>
              </span>
              <span className="reach-check">
                <Icon name="check" />
              </span>
            </div>
          </>
        )}
      </div>
      {profile && profile.devices.length > 0 && (
        <>
          <h3>
            <Trans>Device</Trans>
          </h3>
          <div className="group" role="radiogroup" aria-label={t`Device`}>
            {profile.devices.map((device) => {
              const on = policy?.device_id === device.id;
              return (
                // biome-ignore lint/a11y/useSemanticElements: the reference's own role on its row
                <button
                  key={device.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  disabled={busy}
                  className={`row reach-opt${on ? " on" : ""}`}
                  onClick={() => save({ device_id: device.id })}
                >
                  <span className="row-icon">
                    <Icon name="device" />
                  </span>
                  <span className="body">
                    <strong>
                      <bdi>{device.name}</bdi>
                    </strong>
                    <small>
                      <Trans>A call rings this device · registered for the passkey</Trans>
                    </small>
                  </span>
                  {on && (
                    <span className="reach-check">
                      <Icon name="check" />
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
      <h3>
        <Trans>Per agent</Trans>
      </h3>
      <div className="group">
        {data.agents.map((agent) => (
          <NavRow
            key={agent.id}
            icon={<AgentAvatar agent={agent} />}
            label={<bdi>{agent.name}</bdi>}
            sub={
              rules.value?.[agent.id]?.in_app === false ? t`Notifications off` : t`Notifications on`
            }
            to={`/app/communication/${agent.id}`}
          />
        ))}
      </div>
    </>
  );
}

/* One agent's delivery rules (route `communication`, Q47): in-app alerts, calls, a daily limit.
   Phone notifications stay hidden until a push channel exists (Q10). */
export function CommunicationPage({ agentId }: { agentId: string }) {
  const data = useShellData();
  const toast = useToast();
  const agent = data.agents.find((item) => item.id === agentId);
  const rules = useLoad(
    () => api.get<AgentDeliveryRules>(`/agents/${encodeURIComponent(agentId)}/notifications`),
    [agentId],
  );
  const [draft, setDraft] = useState<AgentDeliveryRules | null>(null);
  const [busy, setBusy] = useState(false);
  if (!agent) return data.agentsLoading ? null : <NotFoundPage />;
  const value = draft ?? rules.value;
  if (!value) return null;
  return (
    <form
      noValidate
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        try {
          rules.set(
            await api.put<AgentDeliveryRules>(
              `/agents/${encodeURIComponent(agentId)}/notifications`,
              value,
            ),
          );
          setDraft(null);
          toast(t`Saved`, { type: "success" });
        } catch (error) {
          toast(userError(error), { type: "error" });
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2>
        <bdi>{agent.name}</bdi>
      </h2>
      <div className="group">
        <ToggleRow
          title={t`In-app messages`}
          on={value.in_app}
          onChange={(in_app) => setDraft({ ...value, in_app })}
        />
        <ToggleRow
          title={t`Agent calls`}
          on={value.calls}
          onChange={(calls) => setDraft({ ...value, calls })}
        />
      </div>
      <Note>
        <Trans>Quiet hours are in Settings ← Notifications and contact.</Trans>
      </Note>
      <label className="field">
        <span>
          <Trans>Daily notification limit</Trans>
        </span>
        <input
          name="limit"
          type="number"
          min={1}
          max={100}
          inputMode="numeric"
          dir="ltr"
          placeholder={t`No limit`}
          value={value.daily_limit ?? ""}
          onChange={(event) => {
            const next = Number.parseInt(event.target.value, 10);
            setDraft({
              ...value,
              daily_limit: Number.isInteger(next) ? Math.min(100, Math.max(1, next)) : null,
            });
          }}
        />
        <small>
          <Trans>Urgent alerts always arrive and do not count.</Trans>
        </small>
      </label>
      <div className="actions">
        <button type="submit" className="btn primary" disabled={busy || !draft}>
          <Trans>Save</Trans>
        </button>
      </div>
    </form>
  );
}
