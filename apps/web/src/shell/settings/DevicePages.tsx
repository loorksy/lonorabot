import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon, type IconName } from "@lonora/ui-web";
import { useEffect, useState } from "react";
import { useShellData } from "../data";
import { useToast } from "../Toast";
import { useAppLock } from "./AppLock";
import {
  A11Y_DEFAULTS,
  type A11yPrefs,
  applyA11y,
  NOTIFY_DEFAULTS,
  type NotifyPrefs,
  useDevicePref,
} from "./device-prefs";
import {
  biometricAvailable,
  enrollBiometric,
  LOCK_DEFAULTS,
  type LockPrefs,
  writeLock,
} from "./lock-state";
import { ToggleRow } from "./ui";

/* «سهولة الاستخدام» (a11yPage 6181-6193): a preview card, the text size slider and two switches,
   applied live on this device. */
export function AccessibilityPage() {
  const [prefs, set] = useDevicePref<A11yPrefs>("a11y", A11Y_DEFAULTS);
  const sizes = [
    t`Small`,
    t({ message: "Default", context: "text size" }),
    t`Large`,
    t`Larger`,
    t`Largest`,
  ];
  useEffect(() => applyA11y(prefs), [prefs]);
  return (
    <>
      <section className="card a11y-preview" aria-hidden="true">
        <div className="msg theirs first">
          <div className="msg-line">
            <div className="bubble">
              <span className="text">
                <Trans>This is how text looks in conversations.</Trans>
              </span>
            </div>
          </div>
        </div>
        <div className="msg mine first">
          <div className="msg-line">
            <div className="bubble">
              <span className="text">
                <Trans>Great, that is clear now.</Trans>
              </span>
            </div>
          </div>
        </div>
      </section>
      <h3>
        <Trans>Text size · {sizes[prefs.size]}</Trans>
      </h3>
      <div className="group pad">
        <div className="size-row">
          <span className="a-sm" aria-hidden="true">
            أ
          </span>
          <input
            type="range"
            min={0}
            max={4}
            step={1}
            value={prefs.size}
            aria-label={t`Text size`}
            aria-valuetext={sizes[prefs.size]}
            onChange={(event) => set({ size: Number(event.target.value) })}
          />
          <span className="a-lg" aria-hidden="true">
            أ
          </span>
        </div>
      </div>
      <h3>
        <Trans>Display</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`Higher contrast`}
          sub={t`Clearer text and borders, opaque backgrounds`}
          on={prefs.contrast}
          icon="eye"
          onChange={(contrast) => set({ contrast })}
        />
        <ToggleRow
          title={t`Reduce motion`}
          sub={t`Stop unnecessary animations and transitions`}
          on={prefs.motion}
          icon="pause"
          onChange={(motion) => set({ motion })}
        />
      </div>
    </>
  );
}

const bytes = (value: number) =>
  value < 1024
    ? t`${Math.round(value)} B`
    : value < 1048576
      ? t`${(value / 1024).toFixed(1)} KB`
      : t`${(value / 1048576).toFixed(2)} MB`;

/** What this browser keeps for Lonora: drafts and unsent messages, settings, and the rest. */
function measure() {
  let messages = 0;
  let settings = 0;
  try {
    for (const key of Object.keys(localStorage)) {
      const size = (key.length + (localStorage.getItem(key)?.length ?? 0)) * 2;
      if (key.startsWith("lonora:composer:") || key.startsWith("lonora:outbox:")) messages += size;
      else if (key.startsWith("lonora")) settings += size;
    }
  } catch {
    /* storage unavailable */
  }
  return { messages, settings };
}

/* «التخزين والبيانات» (storagePage 6145-6157): the space Lonora uses in this browser. Conversations
   live on the server; what is here is the drafts and unsent messages, the device settings and
   the browser's caches. */
export function StoragePage() {
  const [estimate, setEstimate] = useState<{ usage: number; quota: number } | null>(null);
  const [local] = useState(measure);
  useEffect(() => {
    navigator.storage
      ?.estimate?.()
      .then((value) => setEstimate({ usage: value.usage ?? 0, quota: value.quota ?? 0 }))
      .catch(() => setEstimate(null));
  }, []);
  const used = local.messages + local.settings;
  const total = Math.max(used, estimate?.usage ?? 0);
  const cap = estimate?.quota || 5 * 1048576;
  const parts: [string, number, IconName][] = [
    [t`Drafts and unsent messages`, local.messages, "chat"],
    [t`Settings`, local.settings, "settings"],
    [t`Browser cache`, Math.max(0, total - used), "folder"],
  ];
  return (
    <>
      <section className="card store-hero">
        <p className="muted small">
          <Trans>App space in this browser</Trans>
        </p>
        <p className="store-total">
          <b className="ltr">{bytes(total)}</b>
          <small>
            <Trans>of about {bytes(cap)}</Trans>
          </small>
        </p>
        <div
          className="store-bar"
          role="img"
          aria-label={t`${Math.round((total / cap) * 100)}% used`}
        >
          {parts.map(([label, value], index) => (
            <i
              key={label}
              className={`c${index}`}
              style={{ width: `${Math.max(value ? 1 : 0, (value / cap) * 100).toFixed(2)}%` }}
            />
          ))}
        </div>
      </section>
      <div className="group">
        {parts.map(([label, value, icon], index) => (
          <div className="row" key={label}>
            <span className={`row-icon c${index}`}>
              <Icon name={icon} />
            </span>
            <span className="body">
              <strong>{label}</strong>
            </span>
            <span className="value ltr">{bytes(value)}</span>
          </div>
        ))}
      </div>
      <p className="note">
        <Trans>Your conversations and files are kept in Lonora, not in this browser.</Trans>
      </p>
    </>
  );
}

/* «الخصوصية والأمان» (privacyPage 6131-6136) under Q48–Q51: the app lock (code, fingerprint or face
   where the device has it, auto-lock, change the code) and hiding message text. No data actions. */
export function PrivacyPage() {
  const data = useShellData();
  const toast = useToast();
  const lockUi = useAppLock();
  const [lock] = useDevicePref<LockPrefs>("lock", LOCK_DEFAULTS);
  const [notify, setNotify] = useDevicePref<NotifyPrefs>("notify", NOTIFY_DEFAULTS);
  const [bio, setBio] = useState(false);
  useEffect(() => {
    void biometricAvailable().then(setBio);
  }, []);
  const after: [LockPrefs["after"], string][] = [
    [0, t`Immediately`],
    [60, t`After a minute`],
    [900, t`After 15 minutes`],
  ];
  return (
    <>
      <h3>
        <Trans>App lock</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`Lock the app with a code`}
          sub={
            lock.on
              ? t`The code is asked when Lonora opens`
              : t`Protect your conversations with a 4-digit code`
          }
          on={lock.on}
          icon="lock"
          onChange={(on) => {
            if (on) lockUi.setCode();
            else {
              writeLock({ on: false, salt: "", digest: "", credential: null });
              toast(t`App lock turned off`, { type: "success" });
            }
          }}
        />
        {lock.on && (
          <>
            {bio && (
              <ToggleRow
                title={t`Unlock with fingerprint or face`}
                sub={t`Instead of typing the code`}
                on={Boolean(lock.credential)}
                icon="fingerprint"
                onChange={(on) => {
                  if (!on) return writeLock({ credential: null });
                  enrollBiometric(data.owner.email).then(
                    (credential) => {
                      writeLock({ credential });
                      toast(t`Fingerprint or face unlock is on`, { type: "success" });
                    },
                    () => toast(t`The device did not confirm. Try again.`, { type: "warn" }),
                  );
                }}
              />
            )}
            <div className="row">
              <span className="row-icon">
                <Icon name="clock" />
              </span>
              <span className="body">
                <strong>
                  <Trans>Auto-lock</Trans>
                </strong>
                <small>
                  <Trans>After leaving the app</Trans>
                </small>
              </span>
            </div>
            <div className="tabs lock-after" role="radiogroup" aria-label={t`Auto-lock`}>
              {after.map(([value, label]) => (
                // biome-ignore lint/a11y/useSemanticElements: the reference's own role on its row
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={lock.after === value}
                  className={lock.after === value ? "active" : ""}
                  onClick={() => writeLock({ after: value })}
                >
                  {label}
                </button>
              ))}
            </div>
            <button type="button" className="row" onClick={() => lockUi.setCode()}>
              <span className="row-icon">
                <Icon name="key" />
              </span>
              <span className="body">
                <strong>
                  <Trans>Change the code</Trans>
                </strong>
              </span>
              <span className="chevron">
                <Icon name="chev" />
              </span>
            </button>
          </>
        )}
      </div>
      <h3>
        <Trans>Notifications</Trans>
      </h3>
      <div className="group">
        <ToggleRow
          title={t`Hide message text`}
          sub={t`«New message» shows instead of the content`}
          on={!notify.preview}
          icon="eye"
          onChange={(hide) => setNotify({ preview: !hide })}
        />
      </div>
    </>
  );
}
