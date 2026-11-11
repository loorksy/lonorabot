import { t } from "@lingui/core/macro";
import { useLingui } from "@lingui/react";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "../../hooks/useTheme";
import { activateLocale } from "../../i18n/config";
import { api, isRequestCancelled } from "../../lib/api";
import { ownerDisplayName, ownerInitial, useShellData } from "../data";
import { LogoMark } from "../LogoMark";
import { usePopover } from "../lists/Popover";
import { reducedMotion, useDesktop } from "../motion";
import { MOD, useShortcutsSheet } from "../ShortcutsSheet";
import { useSheets } from "../sheets/SheetHost";
import { useDevicePref } from "./device-prefs";
import { LOCK_DEFAULTS, type LockPrefs } from "./lock-state";
import { reachLabel } from "./NotifyPages";
import { NavRow } from "./ui";

const standalone = () =>
  matchMedia("(display-mode: standalone)").matches ||
  Boolean((navigator as Navigator & { standalone?: boolean }).standalone);

/** The integrations count of the root row: linked accounts, configured providers, MCP servers. */
export function useLinkedCount() {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    let live = true;
    Promise.allSettled([
      api.get<unknown[]>("/trading/connections"),
      api.get<{ configured: boolean }[]>("/providers"),
      api.get<unknown[]>("/mcp"),
    ]).then((results) => {
      if (!live) return;
      const [accounts, providers, servers] = results.map((item) =>
        item.status === "fulfilled" ? item.value : [],
      ) as [unknown[], { configured: boolean }[], unknown[]];
      setCount(
        accounts.length + providers.filter((item) => item.configured).length + servers.length,
      );
    });
    return () => {
      live = false;
    };
  }, []);
  return count;
}

type Version = { version: string; build: string | null };

/** The Lonora version and the served build under the sections (Q54: no «حول» page). */
function useVersion() {
  const [version, setVersion] = useState<Version | null>(null);
  useEffect(() => {
    let live = true;
    api.get<Version>("/version").then(
      (value) => {
        if (live) setVersion(value);
      },
      (error) => {
        if (!isRequestCancelled(error)) console.warn("version_unavailable", error);
      },
    );
    return () => {
      live = false;
    };
  }, []);
  return version;
}

/* LanguageSelect + ThemeSwitch in one row (prefsRow, reference 4405-4440). The new theme grows in a
   circle from the switch through a View Transition; reduced motion switches at once. */
function PrefsRow() {
  const { i18n } = useLingui();
  const { theme, setTheme } = useTheme();
  const pop = usePopover();
  const busy = useRef(false);
  const dark = theme !== "light";
  const languages = [
    { id: "ar" as const, name: "العربية", hint: "Arabic" },
    { id: "en" as const, name: "English", hint: "الإنجليزية" },
  ];
  const current = languages.find((item) => item.id === i18n.locale) ?? languages[0];
  const toggle = (button: HTMLElement) => {
    if (busy.current) return;
    const next = dark ? "light" : "dark";
    const start = (
      document as Document & {
        startViewTransition?: (update: () => void) => { finished: Promise<void> };
      }
    ).startViewTransition?.bind(document);
    if (!start || reducedMotion()) return setTheme(next);
    busy.current = true;
    const box = button.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const radius =
      Math.hypot(
        Math.max(innerWidth, screen.width || 0),
        Math.max(innerHeight, screen.height || 0),
      ) * 1.05;
    const root = document.documentElement;
    root.classList.add("theme-vt");
    const transition = start(() => setTheme(next));
    root.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
      {
        duration: 640,
        easing: "cubic-bezier(.4,0,.2,1)",
        pseudoElement: "::view-transition-new(root)",
      },
    );
    transition.finished.finally(() => {
      root.classList.remove("theme-vt");
      busy.current = false;
    });
  };
  return (
    <div className="row prefs-row">
      <button
        type="button"
        className="lang-select"
        aria-haspopup="menu"
        aria-expanded="false"
        aria-label={t`Interface language: ${current.name}`}
        onClick={(event) =>
          pop.open(
            event.currentTarget,
            <>
              <div className="pop-title">
                <Trans>Interface language</Trans>
              </div>
              {languages.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`pop-opt${item.id === current.id ? " on" : ""}`}
                  role="menuitemradio"
                  aria-checked={item.id === current.id}
                  onClick={() => {
                    pop.close();
                    activateLocale(item.id);
                  }}
                >
                  <span className="pop-opt-body">
                    <strong>{item.name}</strong>
                    <small>{item.hint}</small>
                  </span>
                  {item.id === current.id && <Icon name="check" />}
                </button>
              ))}
            </>,
            t`Interface language`,
            { cls: "lang-pop", match: true },
          )
        }
      >
        <Icon name="globe" />
        <span className="ls-name">{current.name}</span>
        <Icon name="down" />
      </button>
      <button
        type="button"
        className={`theme-switch ${dark ? "is-dark" : "is-light"}`}
        role="switch"
        aria-checked={dark}
        aria-label={t`Dark mode`}
        onClick={(event) => toggle(event.currentTarget)}
      >
        <span className="ts-thumb" aria-hidden="true" />
        <span className="ts-ico ts-moon" aria-hidden="true">
          <Icon name="moon" />
        </span>
        <span className="ts-ico ts-sun" aria-hidden="true">
          <Icon name="sun" />
        </span>
      </button>
    </div>
  );
}

function useInstallSheet() {
  const sheets = useSheets();
  const prompt = useRef<(Event & { prompt?: () => Promise<void> }) | null>(null);
  useEffect(() => {
    const keep = (event: Event) => {
      event.preventDefault();
      prompt.current = event;
    };
    window.addEventListener("beforeinstallprompt", keep);
    return () => window.removeEventListener("beforeinstallprompt", keep);
  }, []);
  return () => {
    const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
    const android = /Android/.test(navigator.userAgent);
    const steps = ios
      ? [
          t`Tap the share button at the bottom of the browser.`,
          t`Choose «Add to Home Screen».`,
          t`Tap «Add».`,
        ]
      : android
        ? [
            t`Open the ⋮ menu of the browser.`,
            t`Choose «Install app» or «Add to Home screen».`,
            t`Confirm the installation.`,
          ]
        : [
            t`Click the install icon in the address bar.`,
            t`Or open the browser menu and choose «Install Lonora».`,
            t`It opens in its own window like any app.`,
          ];
    const title = t`Install Lonora`;
    sheets.open({
      id: "install",
      bar: true,
      title,
      label: title,
      body: (
        <>
          <div className="state-hero">
            <LogoMark size={40} />
          </div>
          <p className="state-lead">
            <Trans>Open Lonora straight from your home screen, in a full window.</Trans>
          </p>
          {prompt.current?.prompt ? (
            <div className="actions">
              <button
                type="button"
                className="btn primary full"
                onClick={() => {
                  void prompt.current?.prompt?.();
                  sheets.close();
                }}
              >
                <Trans>Install now</Trans>
              </button>
            </div>
          ) : (
            <>
              <ol className="perm-steps">
                {steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
              <div className="actions">
                <button type="button" className="btn primary full" onClick={() => sheets.close()}>
                  <Trans>OK</Trans>
                </button>
              </div>
            </>
          )}
        </>
      ),
    });
  };
}

/* «الإعدادات» (reference route `settings`): the owner row, then the reference's groups, the
   version line (Q54) and «تسجيل الخروج» with its confirm sheet. */
export function SettingsRoot() {
  const data = useShellData();
  const desktop = useDesktop();
  const sheets = useSheets();
  const shortcuts = useShortcutsSheet();
  const install = useInstallSheet();
  const profile = data.ownerProfile;
  const linked = useLinkedCount();
  const served = useVersion();
  const version = served?.version;
  const build = served?.build?.slice(0, 7);
  const [lock] = useDevicePref<LockPrefs>("lock", LOCK_DEFAULTS);
  const name = ownerDisplayName(profile, data.owner);
  const confirmSignOut = () => {
    const title = t`Sign out?`;
    sheets.open({
      id: "sign-out",
      title,
      label: title,
      body: (
        <>
          <p>
            <Trans>You will need to sign in again. Your conversations stay saved in Lonora.</Trans>
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
                void data.signOut();
              }}
            >
              <Trans>Sign out</Trans>
            </button>
          </div>
        </>
      ),
    });
  };
  return (
    <>
      <div className="group">
        <NavRow
          icon={<span className="avatar initial">{ownerInitial(name)}</span>}
          label={<bdi>{name}</bdi>}
          sub={t`Profile · shared by all your agents`}
          to="/app/owner"
        />
      </div>
      <div className="group">
        <PrefsRow />
        <NavRow icon="chat" label={t`Chat experience`} to="/app/chat-prefs" />
        <NavRow icon="eye" label={t`Accessibility`} to="/app/accessibility" />
      </div>
      <div className="group">
        <NavRow
          icon="bell"
          label={t`Notifications and contact`}
          to="/app/notify-settings"
          value={profile ? reachLabel(profile.reach_me.channel) : undefined}
        />
        <NavRow
          icon="plug"
          label={t`Integrations`}
          to="/app/integrations"
          value={linked ? t`${linked} linked` : undefined}
        />
      </div>
      <div className="group">
        <NavRow icon="chart" label={t`Usage`} to="/app/usage" />
        <NavRow icon="folder" label={t`Storage and data`} to="/app/storage" />
        <NavRow icon="file" label={t`Files`} to="/app/artifacts" />
      </div>
      <div className="group">
        <NavRow
          icon="shield"
          label={t`Privacy and security`}
          to="/app/privacy"
          value={lock.on ? t`Lock on` : undefined}
        />
        {!standalone() && (
          <button type="button" className="row" onClick={install}>
            <Icon name="download" />
            <span className="body">
              <strong>
                <Trans>Install the app</Trans>
              </strong>
            </span>
            <span className="chevron">
              <Icon name="chev" />
            </span>
          </button>
        )}
        {desktop && (
          <button type="button" className="row" onClick={shortcuts}>
            <Icon name="grid" />
            <span className="body">
              <strong>
                <Trans>Keyboard shortcuts</Trans>
              </strong>
            </span>
            <span className="value" dir="ltr">
              {MOD} /
            </span>
          </button>
        )}
      </div>
      <div className="group signout">
        <button type="button" className="row danger-row" onClick={confirmSignOut}>
          <Icon name="back" />
          <span className="body">
            <strong>
              <Trans>Sign out</Trans>
            </strong>
            <small>
              <Trans>
                Signed in as <span className="ltr">{data.owner.email}</span>
              </Trans>
            </small>
          </span>
        </button>
      </div>
      {version && (
        <p className="note settings-version">
          {build ? (
            <Trans>
              Lonora · version {version} · <span className="ltr">{build}</span>
            </Trans>
          ) : (
            <Trans>Lonora · version {version}</Trans>
          )}
        </p>
      )}
    </>
  );
}
