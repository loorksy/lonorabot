/* UI phase 6, calls: the call screen («المكالمة», route `call`), its fold header, the call strip
   on every other screen, the incoming call page («مكالمة واردة», route `incoming`) and the
   call starter that answers Q58 when no voice provider is configured.

   The call itself (WebRTC, the meter, mute) is the voice provider's (`useVoice`). The call
   screen is its expanded view: on `/app/call` the call is open, on any other route it is
   folded, so the route and `voice.minimized` never disagree (Shell keeps them in step). A call
   is provisional speech: it grants no authority, and any trade it leads to still needs its
   own approval card, which this screen shows under the controls. */
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { avatarState } from "@lonora/core";
import { AgentAvatar, Icon } from "@lonora/ui-web";
import { type CSSProperties, type PointerEvent, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { TradeApprovals } from "../../components/trading/TradeApprovals";
import { type CallTarget, useVoice, useVoiceLevels, type VoiceMeter } from "../../hooks/useVoice";
import { type Agent, api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { Empty } from "../domain/ui";
import { useNavigation } from "../navigation";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import "./call.css";

/** Where the call screen folds back to (the reference's `returnView`). */
export const callReturn: { path: string | null } = { path: null };

/** «mm:ss» since the call connected, ticking every second. */
export function useCallClock(startedAt: number | null) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt == null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);
  const seconds = startedAt == null ? 0 : Math.max(0, Math.floor((now - startedAt) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

/** The reference's four-bar wave, driven by this call's real audio levels (transform only). */
function CallWave({ meter, muted }: { meter: VoiceMeter; muted: boolean }) {
  const levels = useVoiceLevels(meter).slice(-4);
  return (
    <div className={`wave${muted ? " muted" : ""}`} aria-hidden="true">
      {levels.map((level, index) => (
        <i
          // biome-ignore lint/suspicious/noArrayIndexKey: four fixed bar positions, no child state.
          key={index}
          style={{ transform: `scaleY(${muted ? 0.25 : 0.35 + level * 1.3})` }}
        />
      ))}
    </div>
  );
}

function BigAvatar({ target, voice }: { target: CallTarget; voice: ReturnType<typeof useVoice> }) {
  return (
    <span className="avatar call-avatar-big">
      <AgentAvatar
        identity={target.agentId}
        name={target.name}
        shape={target.avatar}
        color={target.color}
        tradesOnItsOwn={target.trades_on_its_own}
        tradesOnItsOwnLabel={t`Trades on its own`}
        working={voice.phase === "speaking" && voice.connected}
        state={avatarState({ voice, error: voice.error != null })}
        quality="full"
      />
    </span>
  );
}

/** Leaves the call screen for the view it was opened from; the call keeps running. */
export function foldCall(
  go: (path: string, options?: { replace?: boolean }) => void,
  agentId?: string,
) {
  const back = callReturn.path && !callReturn.path.startsWith("/app/call") ? callReturn.path : null;
  go(back ?? (agentId ? `/app/${agentId}` : "/app"), { replace: true });
}

/** «طي المكالمة» (⌄): on phones it floats at the start, on desktop it follows the name. */
export function CallHeader({ desktop }: { desktop: boolean }) {
  const voice = useVoice();
  const nav = useNavigation();
  const fold = (
    <button
      type="button"
      className="icon"
      aria-label={t`Fold the call`}
      title={t`Fold the call`}
      onClick={() => foldCall(nav.go, voice.target?.agentId)}
    >
      <Icon name="down" />
    </button>
  );
  if (!desktop) return <div className="float-back">{fold}</div>;
  return (
    <header>
      <h1>
        <bdi>{voice.target?.name ?? "Lonora"}</bdi>
      </h1>
      {fold}
    </header>
  );
}

/** «السماعة»: the call's audio output, where the browser lets a page choose it (setSinkId). */
function useSpeaker() {
  const voice = useVoice();
  const sheets = useSheets();
  const toast = useToast();
  const [sink, setSink] = useState("");
  const audio = voice.session?.audio as
    | (HTMLAudioElement & {
        setSinkId?: (id: string) => Promise<void>;
      })
    | undefined;
  const open = async () => {
    if (!audio?.setSinkId || !navigator.mediaDevices?.enumerateDevices) {
      toast(t`This browser does not let a page choose the audio output.`, { type: "warn" });
      return;
    }
    const outputs = (await navigator.mediaDevices.enumerateDevices()).filter(
      (device) => device.kind === "audiooutput",
    );
    if (outputs.length < 2) {
      toast(t`Only one audio output is available.`, { type: "warn" });
      return;
    }
    const choose = async (id: string) => {
      try {
        await audio.setSinkId?.(id);
        setSink(id === "default" ? "" : id);
        sheets.close();
      } catch (cause) {
        toast(userError(cause), { type: "error" });
      }
    };
    sheets.open({
      id: "call-speaker",
      title: t`Audio output`,
      body: (
        <div className="group">
          {outputs.map((device, index) => (
            <button
              type="button"
              className="row"
              key={device.deviceId || index}
              aria-pressed={(sink || "default") === device.deviceId}
              onClick={() => void choose(device.deviceId)}
            >
              <span className="body">
                <strong>
                  <bdi>{device.label || t`Output ${index + 1}`}</bdi>
                </strong>
              </span>
              {(sink || "default") === device.deviceId && <Icon name="check" />}
            </button>
          ))}
        </div>
      ),
    });
  };
  return { on: sink !== "", open };
}

/** «المكالمة»: the full call screen. Pulling it down (or ⌄) folds it into the strip. */
export function CallPage() {
  const voice = useVoice();
  const nav = useNavigation();
  const data = useShellData();
  const clock = useCallClock(voice.startedAt);
  const speaker = useSpeaker();
  const section = useRef<HTMLElement>(null);
  const pull = useRef<{ id: number; y0: number; dy: number } | null>(null);
  const target = voice.target;
  if (!target) return <Empty>{t`There is no call in progress.`}</Empty>;
  const status = voice.ending
    ? t`Ending call`
    : !voice.connected
      ? voice.busy
        ? t`Connecting`
        : t`Call ended`
      : voice.muted
        ? t`Microphone muted`
        : voice.phase === "speaking"
          ? t`Speaking`
          : t`Listening to you`;
  const release = (event: PointerEvent<HTMLElement>) => {
    const current = pull.current;
    if (!current || current.id !== event.pointerId || !section.current) return;
    pull.current = null;
    const node = section.current;
    node.style.transition = "transform .2s var(--ease), opacity .2s";
    if (current.dy > 110) {
      navigator.vibrate?.(8);
      foldCall(nav.go, target.agentId);
    } else {
      node.style.transform = "";
      node.style.opacity = "";
    }
  };
  const retry = () => {
    const agent = data.agents.find((row) => row.id === target.agentId);
    if (agent) void voice.start(agent, target.threadId || null);
  };
  return (
    <section
      ref={section}
      className="call-page"
      aria-label={t`Call with ${target.name}`}
      data-testid="call-view"
      style={{ "--call-color": target.color } as CSSProperties}
      onPointerDown={(event) => {
        if (event.pointerType === "mouse" || (event.target as Element).closest("button")) return;
        pull.current = { id: event.pointerId, y0: event.clientY, dy: 0 };
      }}
      onPointerMove={(event) => {
        const current = pull.current;
        if (!current || current.id !== event.pointerId || !section.current) return;
        current.dy = Math.max(0, event.clientY - current.y0);
        section.current.style.transition = "none";
        section.current.style.transform = `translateY(${current.dy * 0.5}px)`;
        section.current.style.opacity = String(1 - Math.min(0.5, current.dy / 500));
      }}
      onPointerUp={release}
      onPointerCancel={release}
    >
      <p className="muted">
        {t({ message: "Call", context: "call clock" })} ·{" "}
        <span className="ltr" data-clock>
          {clock}
        </span>
      </p>
      <h2>
        <bdi>{target.name}</bdi>
      </h2>
      <BigAvatar target={target} voice={voice} />
      <h2 role="status" className="call-status">
        {status}
      </h2>
      <CallWave meter={voice.meter} muted={voice.muted || !voice.connected} />
      {voice.playbackBlocked && (
        <button type="button" className="btn outline" onClick={() => void voice.playAudio()}>
          <Trans>Play audio</Trans>
        </button>
      )}
      {voice.error != null && (
        <div className="note call-error" role="alert">
          <p>{userError(voice.error)}</p>
          {!voice.session && !voice.busy && (
            <button type="button" className="btn outline" onClick={retry}>
              <Trans>Retry</Trans>
            </button>
          )}
        </div>
      )}
      <div className="call-follow">
        <TradeApprovals
          key={target.threadId}
          threadId={target.threadId}
          since={voice.startedAt ?? Number.POSITIVE_INFINITY}
        />
      </div>
      <div className="call-controls">
        <button
          type="button"
          aria-pressed={voice.muted}
          disabled={!voice.session || voice.ending}
          onClick={voice.toggleMute}
        >
          <span className="circle">
            <Icon name={voice.muted ? "micOff" : "mic"} />
          </span>
          {voice.muted ? t`Unmute` : t({ message: "Mute", context: "call" })}
        </button>
        <button
          type="button"
          aria-pressed={speaker.on}
          disabled={!voice.session || voice.ending}
          onClick={() => void speaker.open()}
        >
          <span className="circle">
            <Icon name="volume" />
          </span>
          {speaker.on ? t({ message: "On", context: "speaker" }) : t`Speaker`}
        </button>
        <button
          type="button"
          disabled={voice.ending}
          onClick={() => void voice.stop().catch(() => undefined)}
        >
          <span className="circle red">
            <Icon name="phone" />
          </span>
          {t({ message: "End", context: "call" })}
        </button>
      </div>
    </section>
  );
}

/** The call folded into its own chat: the header's call button grows into hang up, mute
    and the wave. Tapping the wave returns to the call screen. */
export function CallCapsule() {
  const voice = useVoice();
  if (!voice.target) return null;
  return (
    <fieldset className={`call-pill enter${voice.muted ? " muted" : ""}`}>
      <legend className="sr-only">{t`Ongoing call`}</legend>
      <button
        type="button"
        className="cp-wave"
        data-testid="active-call-pill"
        aria-label={t`Return to the call`}
        title={t`Return to the call`}
        onClick={voice.expand}
      >
        <span className="cp-bars" aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
          <i />
        </span>
      </button>
      <button
        type="button"
        className="cp-btn cp-mute"
        aria-pressed={voice.muted}
        aria-label={voice.muted ? t`Unmute` : t({ message: "Mute", context: "call" })}
        title={voice.muted ? t`Unmute` : t({ message: "Mute", context: "call" })}
        disabled={!voice.session || voice.ending}
        onClick={voice.toggleMute}
      >
        <Icon name={voice.muted ? "micOff" : "mic"} />
      </button>
      <button
        type="button"
        className="cp-btn cp-end"
        aria-label={t`End the call`}
        title={t`End the call`}
        disabled={voice.ending}
        onClick={() => void voice.stop().catch(() => undefined)}
      >
        <Icon name="phone" />
      </button>
    </fieldset>
  );
}

/** The call strip under the top bar on every screen but the call and its own chat. */
export function CallStrip({ hidden }: { hidden: boolean }) {
  const voice = useVoice();
  const clock = useCallClock(voice.startedAt);
  const target = voice.target;
  if (!target || hidden) return null;
  return (
    <div className="call-strip">
      <Icon name="phone" />
      <button
        type="button"
        className="label"
        aria-label={t`Return to the call with ${target.name}`}
        onClick={voice.expand}
      >
        <bdi>{target.name}</bdi> · {voice.muted ? t`Muted` : t`In progress`} ·{" "}
        <span className="ltr" data-clock>
          {clock}
        </span>
      </button>
      <button
        type="button"
        className="icon"
        aria-label={voice.muted ? t`Unmute` : t({ message: "Mute", context: "call" })}
        aria-pressed={voice.muted}
        disabled={!voice.session || voice.ending}
        onClick={voice.toggleMute}
      >
        <Icon name={voice.muted ? "micOff" : "mic"} />
      </button>
      <button
        type="button"
        className="icon"
        aria-label={t({ message: "End", context: "call" })}
        disabled={voice.ending}
        onClick={() => void voice.stop().catch(() => undefined)}
      >
        <Icon name="close" />
      </button>
    </div>
  );
}

type VoiceReadiness = { transport_configured: boolean };

/** Starts a call, or answers Q58: with no voice provider configured nothing is dialled and the
    owner gets the warning with the way to the provider settings. */
export function useCallStarter() {
  const voice = useVoice();
  const sheets = useSheets();
  const nav = useNavigation();
  const toast = useToast();
  const notConfigured = () =>
    sheets.open({
      id: "voice-not-configured",
      title: t`Calls are not set up`,
      body: (
        <>
          <p>
            <Trans>
              No voice provider is configured yet. Add an OpenAI key in the model providers to make
              calls.
            </Trans>
          </p>
          <div className="actions">
            <button type="button" className="btn" onClick={() => sheets.close()}>
              <Trans>Cancel</Trans>
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={() => {
                sheets.close();
                nav.go("/app/provider/openai");
              }}
            >
              <Trans>Set up the voice provider</Trans>
            </button>
          </div>
        </>
      ),
    });
  /** True when the voice provider is configured (otherwise the warning is open). */
  const ready = async () => {
    try {
      const status = await api.get<VoiceReadiness>("/voice/status");
      if (status.transport_configured) return true;
      notConfigured();
    } catch (cause) {
      toast(userError(cause), { type: "error" });
    }
    return false;
  };
  return {
    ready,
    notConfigured,
    start: async (agent: Agent, thread?: string | null) => {
      // One call at a time: the header's call reads «فتح المكالمة الجارية» while one runs.
      if (voice.target) {
        voice.expand();
        return;
      }
      if (await ready()) await voice.start(agent, thread ?? null);
    },
  };
}

export type IncomingCall = {
  id: string;
  agent_id: string;
  thread_id: string;
  status: "ringing" | "accepted" | "rejected" | "missed" | "cancelled";
  reason: string;
  expires_at: string;
  execution_authorized: false;
};
type IncomingPolicy = { channel: string; device_id: string | null };

const ringing = (row: IncomingCall, now = Date.now()) =>
  row.status === "ringing" && Date.parse(row.expires_at) > now;

/** Opens «مكالمة واردة» when an Agent's call rings this owner (reach-me channel «مكالمة»).
    The server decides everything; the page only shows a ringing invitation once. */
export function useIncomingCalls(active: boolean) {
  const nav = useNavigation();
  const seen = useRef(new Set<string>());
  const go = useRef(nav.go);
  go.current = nav.go;
  useEffect(() => {
    if (!active) return;
    let live = true;
    let calls = false;
    let checked = 0;
    const tick = async () => {
      try {
        if (Date.now() - checked > 60_000) {
          const policy = await api.get<IncomingPolicy>("/voice/incoming/policy");
          calls = policy.channel === "call" && !!policy.device_id;
          checked = Date.now();
        }
        if (!calls || !live) return;
        const rows = await api.get<IncomingCall[]>("/voice/incoming");
        const call = rows.find((row) => ringing(row) && !seen.current.has(row.id));
        if (call && live && !location.pathname.startsWith("/app/incoming")) {
          seen.current.add(call.id);
          go.current(`/app/incoming/${call.id}`);
        }
      } catch {
        /* the next tick asks again */
      }
    };
    void tick();
    const timer = setInterval(() => void tick(), 3000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [active]);
}

/** «مكالمة واردة»: the Agent, why it calls, رد · رفض, and «الرد برسالة». */
export function IncomingPage() {
  const { callId: id = "" } = useParams();
  const nav = useNavigation();
  const data = useShellData();
  const toast = useToast();
  const starter = useCallStarter();
  const [call, setCall] = useState<IncomingCall | null | undefined>(undefined);
  const [device, setDevice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    void Promise.all([
      api.get<IncomingCall[]>("/voice/incoming"),
      api.get<IncomingPolicy>("/voice/incoming/policy"),
    ])
      .then(([rows, policy]) => {
        if (!live) return;
        setCall(rows.find((row) => row.id === id && ringing(row)) ?? null);
        setDevice(policy.device_id);
      })
      .catch(() => live && setCall(null));
    return () => {
      live = false;
    };
  }, [id]);
  const agent = call ? data.agents.find((row) => row.id === call.agent_id) : undefined;
  if (call === undefined) return null;
  if (!call || !agent || !device) return <Empty>{t`This call has ended.`}</Empty>;
  const chat = `/app/${agent.id}`;
  const respond = async (action: "accept" | "reject") => {
    if (busy) return;
    // Q58: with no voice provider an answer could not connect, so it is not sent.
    if (action === "accept" && !(await starter.ready())) return;
    setBusy(true);
    try {
      const result = await api.post<IncomingCall>(
        `/voice/incoming/${encodeURIComponent(call.id)}/respond`,
        { action, device_id: device },
      );
      if (action === "accept" && result.status === "accepted" && !result.execution_authorized) {
        callReturn.path = chat;
        nav.go(chat, { replace: true });
        await starter.start(agent, result.thread_id);
        return;
      }
      if (action === "accept") toast(t`This call has ended.`, { type: "warn" });
      nav.go(chat, { replace: true });
    } catch (cause) {
      toast(userError(cause), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="call-page" aria-label={t`Incoming call from ${agent.name}`}>
      <span className="avatar call-avatar-big">
        <AgentAvatar
          identity={agent.id}
          name={agent.name}
          shape={agent.avatar}
          color={agent.color}
          tradesOnItsOwn={agent.trades_on_its_own}
          tradesOnItsOwnLabel={t`Trades on its own`}
          quality="full"
        />
      </span>
      <h2>
        <bdi>{agent.name}</bdi>
      </h2>
      <p className="muted">
        <Trans>Incoming call</Trans>
      </p>
      <p dir="auto">{call.reason}</p>
      <div className="call-controls">
        <button type="button" disabled={busy} onClick={() => void respond("accept")}>
          <span className="circle green">
            <Icon name="phone" />
          </span>
          {t({ message: "Answer", context: "call" })}
        </button>
        <button type="button" disabled={busy} onClick={() => void respond("reject")}>
          <span className="circle red">
            <Icon name="phone" />
          </span>
          {t({ message: "Decline", context: "call" })}
        </button>
      </div>
      <button type="button" className="btn outline" onClick={() => nav.go(chat, { replace: true })}>
        <Trans>Reply with a message</Trans>
      </button>
    </section>
  );
}
