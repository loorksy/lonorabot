import { useLingui } from "@lingui/react";
import { Trans } from "@lingui/react/macro";
import {
  type OwnerProfileLabel,
  ownerProfileLabel,
  type ReachMe,
  type ReplyLanguage,
  reachMeChannels,
  reachMeHint,
  reachMeLabel,
  replyLanguageLabel,
  replyLanguages,
} from "@lonora/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import { MemoryRevisions } from "./MemoryRevisions";

/** The stored reach-me preference; its channel alone decides whether calls ring. */
type ReachPolicy = {
  channel: ReachMe;
  enabled: boolean;
  device_id: string | null;
  opportunities: boolean;
  action_required: boolean;
  critical: boolean;
  timezone: string;
  quiet_start_hour: number | null;
  quiet_end_hour: number | null;
  ttl_seconds: number;
  minimum_interval_seconds: number;
};
type OwnerProfile = {
  content: string;
  version: number;
  reply_language: "ar" | "en" | null;
  reach_me: ReachPolicy;
  devices: { id: string; name: string }[];
  limit: number;
};

type Form = "profile" | "reach";

function hour(value: string): number | null {
  const parsed = Number.parseInt(value, 10);
  return value.trim() && Number.isInteger(parsed) && parsed >= 0 && parsed <= 23 ? parsed : null;
}

/** The one owner profile every agent reads, the reach-me preference and their history. */
export function OwnerProfileSection() {
  const { i18n } = useLingui();
  const locale = i18n.locale;
  const label = (key: OwnerProfileLabel) => ownerProfileLabel(key, locale);
  const { revision, refresh } = useClient();
  const [profile, setProfile] = useState<OwnerProfile | null>(null);
  const [content, setContent] = useState("");
  const [textVersion, setTextVersion] = useState<number | null>(null);
  const [reach, setReach] = useState<ReachPolicy | null>(null);
  const [language, setLanguage] = useState<ReplyLanguage>("auto");
  const [quietStart, setQuietStart] = useState("");
  const [quietEnd, setQuietEnd] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<Form | null>(null);
  // Each form keeps its own unsaved edits: saving one never discards the other's.
  const dirty = useRef<Record<Form, boolean>>({ profile: false, reach: false });
  const apply = useCallback((value: OwnerProfile, savedForm?: Form) => {
    if (savedForm) dirty.current[savedForm] = false;
    setProfile(value);
    // An unsaved text edit keeps the version it started from, so saving over a newer
    // change (an agent's, or another device's) is refused instead of lost.
    if (!dirty.current.profile) {
      setContent(value.content);
      setTextVersion(value.version);
    }
    if (!dirty.current.reach) {
      setReach(value.reach_me);
      setLanguage(value.reply_language ?? "auto");
      setQuietStart(value.reach_me.quiet_start_hour?.toString() ?? "");
      setQuietEnd(value.reach_me.quiet_end_hour?.toString() ?? "");
    }
  }, []);
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<OwnerProfile>("/owner/profile")
      .then((value) => {
        if (live) {
          apply(value);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (live) setError(cause);
      });
    return () => {
      live = false;
    };
  }, [revision, apply]);
  const edit = (form: Form) => {
    dirty.current[form] = true;
    setSaved(null);
  };
  const run = async (kind: Form, action: () => Promise<OwnerProfile>) => {
    setBusy(true);
    setError(undefined);
    setSaved(null);
    try {
      apply(await action(), kind);
      setSaved(kind);
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  };
  const devices = profile?.devices ?? [];
  return (
    <>
      <section className="card owner-profile" aria-label={label("title")}>
        <h2>{label("title")}</h2>
        <p className="muted">{label("shared")}</p>
        {error != null && (
          <div role="alert">
            <p>{userError(error)}</p>
            <button
              type="button"
              onClick={() => {
                dirty.current = { profile: false, reach: false };
                setError(undefined);
                refresh();
              }}
            >
              <Trans>Reload</Trans>
            </button>
          </div>
        )}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!profile || textVersion === null || busy) return;
            void run("profile", () =>
              api.put<OwnerProfile>("/owner/profile", { content, version: textVersion }),
            );
          }}
        >
          <label>
            {label("profile")}
            <textarea
              dir="auto"
              rows={10}
              maxLength={profile?.limit}
              value={content}
              disabled={!profile || busy}
              onChange={(event) => {
                edit("profile");
                setContent(event.target.value);
              }}
            />
          </label>
          <div className="actions">
            {saved === "profile" && <span role="status">{label("saved")}</span>}
            <button type="submit" className="primary" disabled={!profile || busy}>
              {label("save")}
            </button>
          </div>
        </form>
      </section>
      {reach && profile && (
        <form
          className="card reach-me"
          aria-label={label("reachMe")}
          onSubmit={(event) => {
            event.preventDefault();
            if (busy) return;
            // The channel decides whether calls ring; the derived flag is not sent.
            void run("reach", () =>
              api.put<OwnerProfile>("/owner/preferences", {
                reply_language: language === "auto" ? null : language,
                reach_me: {
                  channel: reach.channel,
                  device_id:
                    reach.channel === "call" && !reach.device_id
                      ? (devices[0]?.id ?? null)
                      : reach.device_id,
                  opportunities: reach.opportunities,
                  action_required: reach.action_required,
                  critical: reach.critical,
                  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || reach.timezone,
                  quiet_start_hour: hour(quietStart),
                  quiet_end_hour: hour(quietEnd),
                  ttl_seconds: reach.ttl_seconds,
                  minimum_interval_seconds: reach.minimum_interval_seconds,
                },
              }),
            );
          }}
        >
          <fieldset>
            <legend>{label("reachMe")}</legend>
            {reachMeChannels.map((channel) => (
              <label className="check" key={channel}>
                <input
                  type="radio"
                  name="reach-me"
                  value={channel}
                  checked={reach.channel === channel}
                  disabled={busy || (channel === "call" && devices.length === 0)}
                  onChange={() => {
                    edit("reach");
                    // Choosing calls means being called when a decision is needed.
                    setReach({
                      ...reach,
                      channel,
                      action_required: channel === "call" ? true : reach.action_required,
                    });
                  }}
                />
                <span>
                  {reachMeLabel(channel, locale)}
                  <small className="muted"> {reachMeHint(channel, locale)}</small>
                </span>
              </label>
            ))}
            {devices.length === 0 && <p className="muted">{label("noDevice")}</p>}
          </fieldset>
          {reach.channel === "call" && devices.length > 0 && (
            <>
              <label>
                {label("device")}
                <select
                  value={reach.device_id ?? devices[0]?.id ?? ""}
                  onChange={(event) => {
                    edit("reach");
                    setReach({ ...reach, device_id: event.target.value });
                  }}
                >
                  {devices.map((device) => (
                    <option key={device.id} value={device.id}>
                      {device.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={reach.action_required}
                  onChange={(event) => {
                    edit("reach");
                    setReach({ ...reach, action_required: event.target.checked });
                  }}
                />
                {label("actionRequiredCalls")}
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={reach.opportunities}
                  onChange={(event) => {
                    edit("reach");
                    setReach({ ...reach, opportunities: event.target.checked });
                  }}
                />
                {label("opportunityCalls")}
              </label>
            </>
          )}
          <fieldset>
            <legend>{label("quietHours")}</legend>
            <label>
              {label("quietStart")}
              <input
                inputMode="numeric"
                value={quietStart}
                onChange={(event) => {
                  edit("reach");
                  setQuietStart(event.target.value);
                }}
              />
            </label>
            <label>
              {label("quietEnd")}
              <input
                inputMode="numeric"
                value={quietEnd}
                onChange={(event) => {
                  edit("reach");
                  setQuietEnd(event.target.value);
                }}
              />
            </label>
          </fieldset>
          <label>
            {label("replyLanguage")}
            <select
              value={language}
              onChange={(event) => {
                edit("reach");
                setLanguage(event.target.value as ReplyLanguage);
              }}
            >
              {replyLanguages.map((value) => (
                <option key={value} value={value}>
                  {replyLanguageLabel(value, locale)}
                </option>
              ))}
            </select>
          </label>
          <p className="muted">{label("inAppOnly")}</p>
          <div className="actions">
            {saved === "reach" && <span role="status">{label("saved")}</span>}
            <button type="submit" className="primary" disabled={busy}>
              {label("save")}
            </button>
          </div>
        </form>
      )}
      <MemoryRevisions
        url="/owner/profile/revisions"
        revision={revision}
        version={(document) => (document === "owner_profile" ? profile?.version : undefined)}
        onRestored={(document) => {
          // An undo replaces what that form shows; the other form keeps its edits.
          dirty.current[document === "owner_preferences" ? "reach" : "profile"] = false;
          refresh();
        }}
      />
    </>
  );
}
