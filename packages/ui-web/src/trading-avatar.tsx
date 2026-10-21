import type { CSSProperties, HTMLAttributes } from "react";
import { useEffect, useEffectEvent, useId, useRef } from "react";
import "./trading-avatar.css";
import type { AvatarController, AvatarStateId } from "@lonora/core";
import { GEOMETRY, mount, REST_PATHS, REST_STROKES, REST_WIDTHS, STATE_IDS } from "@lonora/core";

/** The 20 available states. The resting glyph is four trading candles; in each state one liquid mass takes the shape of the job's icon. */
export type TradingAvatarState = AvatarStateId;
export const TRADING_AVATAR_STATES = STATE_IDS;

export interface TradingAvatarProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  state?: TradingAvatarState;
  /** Diameter of the sphere, e.g. 72, "8rem", "100%". */
  size?: number | string;
  /** 1 = normal, 2 = twice as fast (clamped to 0.25 … 4). */
  speed?: number;
  paused?: boolean;
  /** Sphere colour. */
  primaryColor?: string;
  /** Tint of the "active" mass. Semantic states (success / error / warning / angry) keep their own colour. */
  accentColor?: string;
  /** "full" = liquid + glow + glossy highlight (best for big avatars) · "lite" = liquid + glow · "flat" = liquid only. */
  quality?: "full" | "lite" | "flat";
  /** Where the face looks: "pointer" (follows the pointer, wanders when idle), "idle", or "off". */
  look?: "pointer" | "idle" | "off";
  /** Tap / click pushes the face in with a spring. */
  interactive?: boolean;
  label?: string;
}

const { face } = GEOMETRY;
const pill = { x: face.x, y: face.y, width: face.width, height: face.height, rx: face.rx };
const strokeProps = {
  fill: "none",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function TradingAvatar({
  state = "waiting",
  size = 160,
  speed = 1,
  paused = false,
  primaryColor = "#7776ee",
  accentColor,
  quality = "full",
  look = "pointer",
  interactive = true,
  label,
  style,
  className = "",
  ...rest
}: TradingAvatarProps) {
  const uid = `mta${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const rootRef = useRef<HTMLSpanElement>(null);
  const ctl = useRef<AvatarController | null>(null);
  const currentOptions = useEffectEvent(() => ({
    state,
    speed,
    paused,
    accent: accentColor,
    look,
  }));

  useEffect(() => {
    if (!rootRef.current) return;
    ctl.current = mount(rootRef.current, { ...currentOptions(), interactive });
    return () => {
      ctl.current?.destroy();
      ctl.current = null;
    };
  }, [interactive]);
  useEffect(() => {
    ctl.current?.setState(state);
    ctl.current?.setSpeed(speed);
    ctl.current?.setPaused(paused);
    ctl.current?.setAccent(accentColor);
    ctl.current?.setLook(look);
  }, [state, speed, paused, accentColor, look]);

  const dimension = typeof size === "number" ? `${size}px` : size;
  const cssVars = {
    "--mta-primary": primaryColor,
    width: dimension,
    height: dimension,
    ...style,
  } as CSSProperties;

  return (
    <span
      ref={rootRef}
      className={`mta-avatar ${className}`.trim()}
      data-state={state}
      data-paused={paused ? "true" : "false"}
      style={cssVars}
      role="img"
      aria-label={label || `Trading agent: ${state}`}
      {...rest}
    >
      <svg
        className="mta-svg"
        viewBox={GEOMETRY.viewBox}
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <clipPath id={`${uid}-clip`}>
            <rect {...pill} />
          </clipPath>
          <radialGradient id={`${uid}-shade`} cx=".34" cy=".27" r=".95">
            <stop offset="0" stopColor="#fff" stopOpacity=".4" />
            <stop offset=".38" stopColor="#fff" stopOpacity="0" />
            <stop offset=".6" stopColor="#000" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity=".42" />
          </radialGradient>
          <radialGradient id={`${uid}-gloss`} cx=".5" cy=".5" r=".5">
            <stop offset="0" stopColor="#fff" stopOpacity=".5" />
            <stop offset="1" stopColor="#fff" stopOpacity="0" />
          </radialGradient>
          {/* the "liquid" filter: blur + alpha threshold fuses every particle into ONE mass */}
          <filter
            id={`${uid}-goo`}
            filterUnits="userSpaceOnUse"
            x={face.x}
            y={face.y}
            width={face.width}
            height={face.height}
            colorInterpolationFilters="sRGB"
          >
            <feGaussianBlur data-mta-goo="" in="SourceGraphic" stdDeviation="1.65" result="b" />
            <feColorMatrix
              in="b"
              type="matrix"
              values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 20 -9.5"
              result="g"
            />
            {quality !== "flat" && <feGaussianBlur in="g" stdDeviation="9" result="gl0" />}
            {quality !== "flat" && (
              <feColorMatrix
                in="gl0"
                type="matrix"
                values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 .5 0"
                result="gl"
              />
            )}
            {quality === "full" && <feGaussianBlur in="g" stdDeviation="2.4" result="bump" />}
            {quality === "full" && (
              <feSpecularLighting
                in="bump"
                surfaceScale="6"
                specularConstant=".9"
                specularExponent="26"
                lightingColor="#fff"
                result="sp"
              >
                <fePointLight x="150" y="105" z="95" />
              </feSpecularLighting>
            )}
            {quality === "full" && <feComposite in="sp" in2="g" operator="in" result="sp2" />}
            <feMerge>
              {quality !== "flat" && <feMergeNode in="gl" />}
              <feMergeNode in="g" />
              {quality === "full" && <feMergeNode in="sp2" />}
            </feMerge>
          </filter>
        </defs>
        <circle className="mta-shell" cx="200" cy="200" r="177" />
        <circle cx="200" cy="200" r="177" fill={`url(#${uid}-shade)`} />
        <g data-mta-face>
          <rect className="mta-face" {...pill} />
          <g clipPath={`url(#${uid}-clip)`}>
            <g data-mta-bars>
              <g filter={`url(#${uid}-goo)`}>
                {REST_PATHS.map((d, i) => (
                  <path
                    // biome-ignore lint/suspicious/noArrayIndexKey: fixed particle slots never reorder.
                    key={i}
                    className="mta-bar"
                    data-mta-bar={i}
                    d={d}
                    strokeWidth={REST_WIDTHS[i]}
                    style={{ stroke: REST_STROKES[i] }}
                    {...strokeProps}
                  />
                ))}
              </g>
            </g>
          </g>
        </g>
        <g data-mta-gloss>
          <ellipse
            cx="150"
            cy="82"
            rx="86"
            ry="38"
            transform="rotate(-24 150 82)"
            fill={`url(#${uid}-gloss)`}
            opacity=".55"
          />
        </g>
      </svg>
    </span>
  );
}

export default TradingAvatar;
