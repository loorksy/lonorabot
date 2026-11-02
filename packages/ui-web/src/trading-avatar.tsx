import {
  AvatarMotion,
  type AvatarStateId,
  CAT_AVATAR_ASSETS,
  CAT_AVATAR_VIEWBOX,
  catAvatarSignals,
  STATE_IDS,
} from "@lonora/core";
import type { CSSProperties, HTMLAttributes } from "react";
import { useEffect, useRef } from "react";
import "./trading-avatar.css";

export type TradingAvatarState = AvatarStateId;
export const TRADING_AVATAR_STATES = STATE_IDS;

export interface TradingAvatarProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  state?: TradingAvatarState;
  size?: number | string;
  speed?: number;
  paused?: boolean;
  /** Saved identity metadata; agents now share the supplied cat appearance. */
  primaryColor?: string;
  accentColor?: string;
  quality?: "full" | "lite" | "flat";
  look?: "pointer" | "idle" | "off";
  interactive?: boolean;
  label?: string;
}

/** Original 3D shell + live vector signals. No WebGL contexts or network fetches. */
export function TradingAvatar({
  state = "waiting",
  size = 160,
  speed = 1,
  paused = false,
  primaryColor: _primaryColor,
  accentColor: _accentColor,
  quality: _quality,
  look: _look,
  interactive = true,
  label,
  style,
  className = "",
  ...rest
}: TradingAvatarProps) {
  const rootRef = useRef<HTMLSpanElement>(null);
  const sampler = useRef<AvatarMotion | null>(null);
  if (!sampler.current) sampler.current = new AvatarMotion(state);
  const options = useRef({ state, speed, paused });
  options.current = { state, speed, paused };
  const refresh = useRef<(() => void) | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    const motion = sampler.current;
    if (!root || !motion) return;
    const paths = [...root.querySelectorAll<SVGPathElement>("[data-cat-signal]")];
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    let visible = true;
    let frame = 0;
    let previous = 0;
    let destroyed = false;
    const paint = (dt = 0) => {
      motion.setState(options.current.state);
      const signals = catAvatarSignals(motion.frame(dt, reduced.matches));
      for (const [index, path] of paths.entries()) {
        const signal = signals[index];
        path.setAttribute("d", signal.path);
        path.setAttribute("stroke-width", String(signal.width));
        path.setAttribute("opacity", String(signal.opacity));
      }
    };
    const animate = () =>
      !destroyed &&
      visible &&
      !document.hidden &&
      !options.current.paused &&
      !reduced.matches &&
      (!["waiting", "success", "error", "warning", "sleeping", "celebrating"].includes(
        options.current.state,
      ) ||
        root.getBoundingClientRect().width >= 64);
    const draw = (now: number) => {
      frame = 0;
      if (!animate()) return;
      if (!previous || now - previous >= 1000 / 30) {
        const rate = Number.isFinite(options.current.speed)
          ? Math.max(0.25, Math.min(4, options.current.speed))
          : 1;
        paint(previous ? ((now - previous) / 1000) * rate : 0);
        previous = now;
      }
      frame = requestAnimationFrame(draw);
    };
    const sync = () => {
      cancelAnimationFrame(frame);
      previous = 0;
      paint();
      frame = animate() ? requestAnimationFrame(draw) : 0;
    };
    refresh.current = sync;
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    });
    observer.observe(root);
    reduced.addEventListener("change", sync);
    document.addEventListener("visibilitychange", sync);
    sync();
    return () => {
      destroyed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      reduced.removeEventListener("change", sync);
      document.removeEventListener("visibilitychange", sync);
      refresh.current = null;
    };
  }, []);
  // biome-ignore lint/correctness/useExhaustiveDependencies: refresh reads current options through a ref.
  useEffect(() => refresh.current?.(), [state, speed, paused]);

  const signals = catAvatarSignals(sampler.current.frame(0));
  const dimension = typeof size === "number" ? `${size}px` : size;
  return (
    <span
      ref={rootRef}
      className={`lonora-cat-avatar ${className}`.trim()}
      data-state={state}
      data-paused={paused}
      data-interactive={interactive}
      style={{ width: dimension, height: dimension, ...style } as CSSProperties}
      role="img"
      aria-label={label || `Trading agent: ${state}`}
      {...rest}
    >
      <svg viewBox={CAT_AVATAR_VIEWBOX} aria-hidden="true" focusable="false">
        <image
          className="lonora-cat-night"
          href={CAT_AVATAR_ASSETS.night}
          width="400"
          height="400"
        />
        <image className="lonora-cat-day" href={CAT_AVATAR_ASSETS.day} width="400" height="400" />
        {signals.map((signal, index) => (
          <path
            // biome-ignore lint/suspicious/noArrayIndexKey: fixed particle slots never reorder.
            key={index}
            data-cat-signal={index}
            d={signal.path}
            strokeWidth={signal.width}
            opacity={signal.opacity}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
      </svg>
    </span>
  );
}

export default TradingAvatar;
