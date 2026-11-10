import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon, type IconName } from "@lonora/ui-web";
import { type FormEvent, type ReactNode, useState } from "react";
import { auth, type Owner } from "../../lib/auth";
import { initializeOwner } from "../../lib/bootstrap";
import { userError } from "../../lib/user_error";
import { LogoMark } from "../LogoMark";
import "./settings.css";

/* The #auth layer (reference authRender 6006-6052) under Q46: the intro slides (once per device),
   e-mail + password sign-in, «انتهت جلستك» after the server ends the session, and the first-run
   step that creates the owner with the setup token. No phone/OTP, sign-up or forgot-password: a
   single-owner product. The steps are one list so a hosted product can add its own later. */
type Step = "intro" | "signin" | "expired" | "bootstrap";
const INTRO_KEY = "lonora.auth.intro-seen";
const introSeen = () => {
  try {
    return localStorage.getItem(INTRO_KEY) === "1";
  } catch {
    return true;
  }
};

function Field({
  label,
  name,
  type = "text",
  ...rest
}: {
  label: ReactNode;
  name: string;
  type?: string;
} & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="field">
      <span>{label}</span>
      <input name={name} type={type} {...rest} />
    </label>
  );
}

export function AuthFlow({
  initialized,
  expired = false,
  intro = false,
  onLogin,
}: {
  initialized: boolean;
  expired?: boolean;
  /** The owner signed out: the intro opens again, as in the reference. */
  intro?: boolean;
  onLogin: (owner: Owner) => void;
}) {
  const after: Step = initialized ? (expired ? "expired" : "signin") : "bootstrap";
  const [step, setStepOnly] = useState<Step>(() =>
    introSeen() && initialized && !intro ? after : "intro",
  );
  const [slide, setSlide] = useState(0);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const setStep = (next: Step) => {
    setError(undefined);
    setStepOnly(next);
  };
  const slides: [IconName | "logo", string, string][] = [
    ["logo", t`Welcome to Lonora`, t`Smart agents working for you, all in one conversation.`],
    [
      "users",
      t`Your team of agents`,
      t`Create an agent for each task, and gather them in groups that work together.`,
    ],
    [
      "shield",
      t`You decide`,
      t`No sensitive action runs without a permission you grant, and you can stop it any moment.`,
    ],
  ];
  const leaveIntro = () => {
    try {
      localStorage.setItem(INTRO_KEY, "1");
    } catch {
      /* the intro shows again next time */
    }
    setStep(after);
  };
  const run = async (
    event: FormEvent<HTMLFormElement>,
    action: (form: FormData) => Promise<void>,
  ) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.checkValidity()) {
      setError(new Error(t`Check the highlighted fields.`));
      (form.querySelector(":invalid") as HTMLElement | null)?.focus();
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await action(new FormData(form));
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  const message =
    error == null
      ? ""
      : error instanceof Error && !("code" in error)
        ? error.message
        : userError(error);
  const err = message ? (
    <span className="field-err" role="alert">
      <Icon name="alert" />
      <span>{message}</span>
    </span>
  ) : null;
  let body: ReactNode;
  if (step === "intro") {
    const [icon, title, text] = slides[slide];
    const last = slide === slides.length - 1;
    body = (
      <>
        <div className="auth-top">
          <span />
          {!last && (
            <button type="button" className="link" onClick={leaveIntro}>
              <Trans>Skip</Trans>
            </button>
          )}
        </div>
        <div className="auth-slide" key={slide}>
          <div className="auth-art">
            {icon === "logo" ? <LogoMark size={72} /> : <Icon name={icon} />}
          </div>
          <h1>{title}</h1>
          <p>{text}</p>
        </div>
        <div className="auth-dots" aria-hidden="true">
          {slides.map(([, key], index) => (
            <i key={key} className={index === slide ? "on" : ""} />
          ))}
        </div>
        <div className="auth-actions">
          <button
            type="button"
            className="btn primary full"
            onClick={() => (last ? leaveIntro() : setSlide(slide + 1))}
          >
            {last ? <Trans>Start now</Trans> : <Trans>Next</Trans>}
          </button>
        </div>
      </>
    );
  } else if (step === "expired") {
    body = (
      <div className="auth-body center">
        <div className="auth-art small">
          <Icon name="lock" />
        </div>
        <h1>
          <Trans>Your session ended</Trans>
        </h1>
        <p className="muted">
          <Trans>
            For your account's safety, sign in again. Your conversations and drafts are saved.
          </Trans>
        </p>
        <button type="button" className="btn primary full" onClick={() => setStep("signin")}>
          <Trans>Sign in</Trans>
        </button>
      </div>
    );
  } else if (step === "signin") {
    body = (
      <>
        <div className="auth-top">
          <span className="auth-logo">
            <LogoMark size={30} />
          </span>
        </div>
        <div className="auth-body">
          <h1>
            <Trans>Sign in</Trans>
          </h1>
          <p className="muted">
            <Trans>Welcome back.</Trans>
          </p>
          <form
            noValidate
            onSubmit={(event) =>
              run(event, async (form) => {
                const login = await auth.login(
                  String(form.get("email")),
                  String(form.get("password")),
                );
                onLogin(login.owner);
              })
            }
          >
            <Field
              label={t`Email`}
              name="email"
              type="email"
              required
              autoComplete="username"
              dir="ltr"
              placeholder="name@example.com"
            />
            <Field
              label={t`Password`}
              name="password"
              type="password"
              required
              autoComplete="current-password"
            />
            {err}
            <button type="submit" className="btn primary full" disabled={busy}>
              <Trans>Sign in</Trans>
            </button>
          </form>
        </div>
      </>
    );
  } else {
    body = (
      <>
        <div className="auth-top">
          <span className="auth-logo">
            <LogoMark size={30} />
          </span>
        </div>
        <div className="auth-body">
          <h1>
            <Trans>Set up Lonora</Trans>
          </h1>
          <p className="muted">
            <Trans>
              Create the owner account with the setup token from your server configuration.
            </Trans>
          </p>
          <form
            noValidate
            onSubmit={(event) =>
              run(event, async (form) => {
                const email = String(form.get("email"));
                const password = String(form.get("password"));
                await initializeOwner(email, password, String(form.get("token")));
                onLogin((await auth.login(email, password)).owner);
              })
            }
          >
            <Field
              label={t`Email`}
              name="email"
              type="email"
              required
              autoComplete="username"
              dir="ltr"
            />
            <Field
              label={t`Password · at least 12 characters`}
              name="password"
              type="password"
              required
              minLength={12}
              autoComplete="new-password"
            />
            <Field
              label={t`Setup token`}
              name="token"
              type="password"
              required
              autoComplete="off"
              dir="ltr"
            />
            {err}
            <button type="submit" className="btn primary full" disabled={busy}>
              <Trans>Create workspace</Trans>
            </button>
          </form>
        </div>
      </>
    );
  }
  return (
    <div className="app-shell">
      <div id="auth" role="dialog" aria-modal="true" aria-label={t`Sign in`}>
        <div className="auth-card">{body}</div>
      </div>
    </div>
  );
}
