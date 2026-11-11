import { t } from "@lingui/core/macro";
import { Icon } from "@lonora/ui-web";
import { useEffect, useRef, useState } from "react";
import type { VoicePart } from "./context";

/* Voice notes (reference ab_voice, Desktop-37 4600-4840): the bubble plays one note at a time;
   the waveform is the progress bar (tap, drag or arrows ±2s to seek); speed 1× · 1.5× · 2×.
   The recorder (long-press the mic 350ms; slide 110px to cancel, 70px up to lock; ≤2:00) uploads
   the opus blob as an artifact; the server transcribes it into the message (Q24). The silent
   recording fallback is dropped: without a microphone the recorder does not start. */
export const VOICE = {
  hold: 350,
  cancel: 110,
  lock: 70,
  min: 0.7,
  max: 120,
  bars: 44,
  live: 32,
  sample: 70,
};
export const voiceFmt = (seconds: number) => {
  const s = Math.max(0, Math.round(seconds || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
/** 44 peaks, 0..100, normalised to the loudest sample (reference voicePeaks). */
export function voicePeaks(levels: number[], n = VOICE.bars): number[] {
  if (!levels.length) return Array(n).fill(15);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const a = Math.floor((i * levels.length) / n);
    const b = Math.max(a + 1, Math.floor(((i + 1) * levels.length) / n));
    let m = 0;
    for (let k = a; k < b && k < levels.length; k++) m = Math.max(m, levels[k]);
    out.push(m);
  }
  const top = Math.max(...out, 0.01);
  return out.map((v) => Math.round(Math.max(0.08, v / top) * 100));
}

/** The one note playing in the app. */
let playing: { stop: () => void } | null = null;

export function VoiceNote({ part, messageId }: { part: VoicePart; messageId: string }) {
  const duration = Math.max(0.1, part.duration || 0.1);
  const peaks = part.peaks?.length ? part.peaks : Array(VOICE.bars).fill(30);
  const [state, setState] = useState({ active: false, playing: false, t: 0, rate: 1 });
  const audio = useRef<HTMLAudioElement | null>(null);
  const frame = useRef(0);
  const self = useRef<{ stop: () => void }>({ stop: () => undefined });
  useEffect(() => {
    self.current.stop = () => {
      audio.current?.pause();
      cancelAnimationFrame(frame.current);
      setState((old) => ({ ...old, active: false, playing: false, t: 0 }));
    };
    return () => {
      cancelAnimationFrame(frame.current);
      audio.current?.pause();
      if (playing === self.current) playing = null;
    };
  }, []);
  const ensure = () => {
    if (!audio.current) {
      const a = new Audio(`/api/artifacts/${encodeURIComponent(part.artifact_id)}/file`);
      a.preload = "auto";
      a.onended = () => {
        setState((old) => ({ ...old, t: duration, playing: false }));
        setTimeout(() => self.current.stop(), 180);
      };
      audio.current = a;
    }
    return audio.current;
  };
  const loop = () => {
    const a = audio.current;
    if (!a || a.paused) return;
    setState((old) => ({ ...old, t: Math.min(duration, a.currentTime) }));
    frame.current = requestAnimationFrame(loop);
  };
  const play = (from?: number) => {
    if (playing && playing !== self.current) playing.stop();
    playing = self.current;
    const a = ensure();
    const start = from ?? (state.t >= duration - 0.05 ? 0 : state.t);
    try {
      a.currentTime = start;
    } catch {
      // not seekable before metadata
    }
    a.playbackRate = state.rate;
    void a.play().catch(() => undefined);
    setState((old) => ({ ...old, active: true, playing: true, t: start }));
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(loop);
  };
  const pause = () => {
    audio.current?.pause();
    cancelAnimationFrame(frame.current);
    setState((old) => ({ ...old, playing: false }));
  };
  const seek = (fraction: number, andPlay = false) => {
    const at = Math.max(0, Math.min(duration, fraction * duration));
    if (!state.active || andPlay) return play(at);
    const a = ensure();
    try {
      a.currentTime = at;
    } catch {
      // ignored
    }
    setState((old) => ({ ...old, t: at }));
  };
  const fraction = state.active ? Math.max(0, Math.min(1, state.t / duration)) : 0;
  const shown = state.playing || state.t > 0 ? state.t : duration;
  const bars = peaks.map((p, i) => (
    // biome-ignore lint/suspicious/noArrayIndexKey: fixed 44 bars
    <i key={i} style={{ height: `${Math.round(16 + (Math.min(100, p) / 100) * 84)}%` }} />
  ));
  const fromPointer = (event: React.PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
    const x = (event.clientX - box.left) / box.width;
    return rtl ? 1 - x : x;
  };
  return (
    <div
      className={`vnote${state.active ? " active" : ""}${state.playing ? " playing" : ""}`}
      data-vmid={messageId}
      style={{ "--p": fraction.toFixed(4) } as React.CSSProperties}
    >
      <button
        type="button"
        className="vplay"
        aria-label={state.playing ? t`Pause` : t`Play voice message (${voiceFmt(duration)})`}
        onClick={() => (state.playing ? pause() : play())}
      >
        <Icon name={state.playing ? "pause" : "play"} />
      </button>
      <div
        className="vwave"
        role="slider"
        tabIndex={0}
        aria-label={t`Playback position`}
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(state.t)}
        aria-valuetext={t`${voiceFmt(state.t)} of ${voiceFmt(duration)}`}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          seek(fromPointer(event), !state.playing && !state.active);
        }}
        onPointerMove={(event) => {
          if (event.buttons) seek(fromPointer(event));
        }}
        onKeyDown={(event) => {
          const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
          const forward = rtl ? "ArrowLeft" : "ArrowRight";
          const back = rtl ? "ArrowRight" : "ArrowLeft";
          if (event.key !== forward && event.key !== back) return;
          event.preventDefault();
          seek((state.t + (event.key === forward ? 2 : -2)) / duration);
        }}
      >
        <span className="vbars">{bars}</span>
        <span className="vbars on" aria-hidden="true">
          {bars}
        </span>
      </div>
      <div className="vside">
        <span className="vtime ltr">{voiceFmt(shown)}</span>
        <button
          type="button"
          className="vspeed"
          dir="ltr"
          aria-label={t`Playback speed`}
          onClick={() => {
            const rate = state.rate === 1 ? 1.5 : state.rate === 1.5 ? 2 : 1;
            if (audio.current) audio.current.playbackRate = rate;
            setState((old) => ({ ...old, rate }));
          }}
        >
          {state.rate}×
        </button>
      </div>
    </div>
  );
}
