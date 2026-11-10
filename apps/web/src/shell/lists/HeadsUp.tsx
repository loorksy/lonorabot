import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import {
  attentionAlwaysShows,
  type ChatRow,
  headsUpAllowed,
  inQuietHours,
  type QuietHours,
  rowKey,
} from "@lonora/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAttentionLabels } from "../../components/ai/AttentionInbox";
import { api, isRequestCancelled } from "../../lib/api";
import { useAttention } from "../../providers/AttentionProvider";
import { useClient } from "../../providers/ClientProvider";
import { useShellData } from "../data";
import { useNavigation } from "../navigation";
import { recoveryPath } from "../routes";
import { suppressClicks } from "../sheets/SheetHost";
import { chatPath } from "./ChatList";
import { useLists } from "./state";
import { RowAvatar } from "./ThreadRow";

/* HeadsUp: an answer that arrives in another chat shows at the top for 5.2s with «رد»; a
   swipe up hides it. Mute, archive and the owner's quiet hours suppress it and its tone
   (owner decision Q4, the reach-me policy); a critical or action_required attention item
   always shows. */
/** `path`: where a tap goes when it is not the row's chat (a broker outage → recovery). */
type Banner = { row: ChatRow; text: string; serial: number; path?: string };

let audio: AudioContext | null = null;
function tone() {
  try {
    audio ??= new AudioContext();
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    const now = audio.currentTime;
    oscillator.frequency.setValueAtTime(880, now);
    oscillator.frequency.exponentialRampToValueAtTime(1320, now + 0.09);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.08, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
    oscillator.connect(gain).connect(audio.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.24);
  } catch {
    /* no sound where audio is unavailable */
  }
}

/** The quiet hours of the owner's reach-me policy, read again when anything changes. */
function useQuietHours() {
  const { revision } = useClient();
  const [quiet, setQuiet] = useState<QuietHours | null>(null);
  useEffect(() => {
    void revision;
    let live = true;
    api
      .get<{ reach_me: QuietHours }>("/owner/profile")
      .then((profile) => {
        if (live) setQuiet(profile.reach_me);
      })
      .catch((error) => {
        if (!isRequestCancelled(error)) console.warn("quiet_hours_unavailable", error);
      });
    return () => {
      live = false;
    };
  }, [revision]);
  return quiet;
}

export function HeadsUp({ currentThreadId }: { currentThreadId?: string }) {
  const { events } = useClient();
  const quiet = useQuietHours();
  const data = useShellData();
  const lists = useLists();
  const attention = useAttention();
  const labels = useAttentionLabels();
  const nav = useNavigation();
  const [banner, setBanner] = useState<Banner | null>(null);
  const [phase, setPhase] = useState<"in" | "out">("out");
  const mounted = useRef(Date.now());
  const cursor = useRef(-1);
  const announced = useRef(new Set<string>());
  const serial = useRef(0);
  const startY = useRef(0);
  const live = useRef({
    rows: lists.rows,
    agents: data.agents,
    current: currentThreadId,
    labels,
    quiet,
  });
  live.current = { rows: lists.rows, agents: data.agents, current: currentThreadId, labels, quiet };
  const show = useCallback((row: ChatRow, text: string, path?: string) => {
    serial.current += 1;
    setBanner({ row, text, serial: serial.current, path });
    setPhase("in");
    tone();
  }, []);
  useEffect(() => {
    const fresh = events.filter((event) => event.cursor > cursor.current);
    if (cursor.current < 0) {
      // What already happened before this page opened is not news.
      cursor.current = Math.max(0, ...events.map((event) => event.cursor));
      return;
    }
    if (!fresh.length) return;
    cursor.current = Math.max(...fresh.map((event) => event.cursor));
    const { rows, agents, current, quiet } = live.current;
    if (inQuietHours(quiet, new Date())) return;
    for (const event of fresh) {
      const payload = event.payload as Record<string, unknown>;
      if (event.kind !== "message.created" || payload.role !== "assistant") continue;
      if (!event.thread_id || event.thread_id === current) continue;
      if (Date.parse(String(payload.created_at ?? "")) < mounted.current - 5000) continue;
      const row = rows.find((candidate) => candidate.threadId === event.thread_id);
      if (!row || !headsUpAllowed(row.entry)) continue;
      const content = typeof payload.content === "string" ? payload.content.trim() : "";
      const speaker =
        row.kind === "group"
          ? agents.find((agent) => agent.id === payload.agent_id)?.name
          : undefined;
      const text = content ? (speaker ? `${speaker}: ${content}` : content) : t`New message`;
      show(row, text.length > 120 ? `${text.slice(0, 120)}…` : text);
    }
  }, [events, show]);
  useEffect(() => {
    const { rows, labels } = live.current;
    for (const item of attention.items) {
      if (announced.current.has(item.id)) continue;
      announced.current.add(item.id);
      if (!attentionAlwaysShows(item.importance)) continue;
      if (Date.parse(item.created_at) < mounted.current - 5000) continue;
      const key = item.parameters.group_id
        ? rowKey("group", item.parameters.group_id)
        : rowKey("agent", item.agent_id);
      const row = rows.find((candidate) => candidate.key === key);
      if (row)
        show(
          row,
          item.parameters.summary || labels[item.code],
          item.code === "broker_degraded" ? recoveryPath(item.parameters.account_id) : undefined,
        );
    }
  }, [attention.items, show]);
  const [entered, setEntered] = useState(0);
  useEffect(() => {
    if (!banner) return;
    // Mount off screen, then slide in on the next frame.
    const frame = requestAnimationFrame(() => setEntered(banner.serial));
    return () => cancelAnimationFrame(frame);
  }, [banner]);
  useEffect(() => {
    if (!banner) return;
    if (phase === "out") {
      const gone = setTimeout(() => setBanner(null), 300);
      return () => clearTimeout(gone);
    }
    const timer = setTimeout(() => setPhase("out"), 5200);
    return () => clearTimeout(timer);
  }, [phase, banner]);
  if (!banner) return null;
  const open = () => {
    setPhase("out");
    nav.go(banner.path ?? chatPath(banner.row));
  };
  return (
    <div
      id="headsup"
      key={banner.serial}
      role="status"
      className={phase === "out" ? "out" : entered === banner.serial ? "in" : ""}
      onPointerDown={(event) => {
        startY.current = event.clientY;
      }}
      onPointerUp={(event) => {
        if (startY.current && event.clientY < startY.current - 24) {
          setPhase("out");
          suppressClicks(300);
        }
        startY.current = 0;
      }}
    >
      <button type="button" className="hu-main" onClick={open}>
        <RowAvatar row={banner.row} agents={data.agents} />
        <span className="hu-t">
          <strong>
            <bdi>{banner.row.name}</bdi>
          </strong>
          <small>
            <bdi>{banner.text}</bdi>
          </small>
        </span>
      </button>
      <button type="button" className="btn small outline hu-reply" onClick={open}>
        {/* A broker outage opens the recovery page under its own words, not «رد». */}
        {banner.path ? <Trans>State details</Trans> : <Trans>Reply</Trans>}
      </button>
    </div>
  );
}
