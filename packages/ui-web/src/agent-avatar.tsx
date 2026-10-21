// Adapted for Lonora from Tampletgrok BotAvatar, RobotAvatar and OrganicAvatar; Apache-2.0.
// Copyright and provenance are retained in THIRD_PARTY_NOTICES.md.
import type { CSSProperties } from "react";
import { memo, useId, useMemo, useSyncExternalStore } from "react";
import {
  AVATAR_CENTER,
  AVATAR_SHAPES,
  AVATAR_VIEWBOX,
  type AvatarColorDef,
  avatarIdentitySeed,
  organicAvatarPath,
  resolveAvatarColor,
} from "./avatar-geometry";
import { cn } from "./lib/utils";
import "./avatar.css";

export const AgentAvatar = memo(function AgentAvatar({
  name,
  color = "#7c83fd",
  shape = "orb",
  working = false,
  superBot = false,
  superBotLabel,
  className,
}: {
  name: string;
  color?: string;
  shape?: string;
  working?: boolean;
  superBot?: boolean;
  superBotLabel?: string;
  className?: string;
}) {
  const id = useId().replace(/[^a-zA-Z0-9-_]/g, "");
  const colorDef = useMemo(() => resolveAvatarColor(name, color), [name, color]);
  const geometricShape = shape === "square" || shape === "diamond" ? "squircle" : shape;
  const shapePath = AVATAR_SHAPES[geometricShape];

  return (
    <span
      className={cn("lonora-agent-avatar", className)}
      data-shape={shape}
      data-working={working}
      data-super-bot={superBot}
      aria-hidden={superBot ? undefined : true}
      role="img"
      aria-label={superBot ? superBotLabel : undefined}
      style={
        {
          "--agent-color": colorDef.hex,
          "--lonora-avatar-light": colorDef.light,
          "--lonora-avatar-dark": colorDef.dark,
        } as CSSProperties
      }
    >
      {shape === "organic" ? (
        <OrganicAvatar colorDef={colorDef} identity={name} isWorking={working} />
      ) : shapePath ? (
        <ShapeAvatar
          colorDef={colorDef}
          shapePath={shapePath}
          diamond={shape === "diamond"}
          isWorking={working}
          gradientId={id}
        />
      ) : (
        <RobotAvatar colorDef={colorDef} isWorking={working} identity={name} gradientId={id} />
      )}
      {superBot && (
        <svg className="lonora-super-bot-mark" viewBox="0 0 20 20" aria-hidden="true">
          <circle cx="10" cy="10" r="10" fill="#191717" />
          <path d="M4 7 7 9 10 4 13 9 16 7 14 14H6Z" fill="#f0c866" />
        </svg>
      )}
    </span>
  );
});

function WorkingRing({ colorDef, gradientId }: { colorDef: AvatarColorDef; gradientId: string }) {
  return (
    <svg className="lonora-bot-avatar-ring" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle
        cx="24"
        cy="24"
        r="22"
        stroke={`url(#${gradientId}-ring)`}
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeDasharray="45 80"
      />
      <circle cx="43" cy="24" r="2.8" fill="#ffffff" />
      <defs>
        <linearGradient id={`${gradientId}-ring`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
          <stop offset="60%" stopColor={colorDef.light} stopOpacity="0.9" />
          <stop offset="100%" stopColor={colorDef.light} stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  );
}

function RobotAvatar({
  colorDef,
  isWorking,
  identity,
  gradientId,
}: {
  colorDef: AvatarColorDef;
  isWorking: boolean;
  identity: string;
  gradientId: string;
}) {
  const seed = avatarIdentitySeed(identity || colorDef.hex);
  const idleDuration = (4.2 + ((seed * 7) % 28) / 10).toFixed(2);
  const idleDelay = (-(((seed * 13) % 45) / 10)).toFixed(2);
  const idleEyeAnimation = {
    "--lonora-eye-animation-name": `lonora-eyes-idle-${seed % 4}`,
    "--lonora-eye-animation-duration": `${idleDuration}s`,
    "--lonora-eye-animation-easing": "cubic-bezier(0.4, 0, 0.2, 1)",
    "--lonora-eye-animation-delay": `${idleDelay}s`,
  } as CSSProperties;
  const workingEyeAnimation = {
    "--lonora-eye-animation-name": "lonora-eyes-working",
    "--lonora-eye-animation-duration": "1.4s",
    "--lonora-eye-animation-easing": "ease-in-out",
    "--lonora-eye-animation-delay": "0s",
  } as CSSProperties;

  return (
    <span
      className="lonora-bot-avatar lonora-robot-avatar"
      data-working={isWorking}
      style={{
        background: `radial-gradient(circle at 35% 26%, ${colorDef.light}, ${colorDef.hex} 55%, ${colorDef.dark} 100%)`,
      }}
    >
      <WorkingRing colorDef={colorDef} gradientId={gradientId} />
      <span className="lonora-bot-avatar-visor">
        {(["idle", "working"] as const).map((mode) => (
          <span
            key={mode}
            className={`lonora-bot-avatar-eyes lonora-bot-avatar-eyes-${mode}`}
            style={mode === "idle" ? idleEyeAnimation : workingEyeAnimation}
          >
            <span className="lonora-bot-avatar-eye" />
            <span className="lonora-bot-avatar-eye" />
          </span>
        ))}
      </span>
    </span>
  );
}

function ShapeAvatar({
  colorDef,
  shapePath,
  diamond,
  isWorking,
  gradientId,
}: {
  colorDef: AvatarColorDef;
  shapePath: string;
  diamond: boolean;
  isWorking: boolean;
  gradientId: string;
}) {
  return (
    <span className="lonora-bot-avatar lonora-shape-avatar" data-working={isWorking}>
      <WorkingRing colorDef={colorDef} gradientId={gradientId} />
      <svg viewBox={AVATAR_VIEWBOX} className="lonora-shape-avatar-svg" aria-hidden="true">
        <defs>
          <linearGradient id={`${gradientId}-ink`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={colorDef.light} />
            <stop offset="100%" stopColor={colorDef.dark} />
          </linearGradient>
        </defs>
        <path
          d={shapePath}
          fill={`url(#${gradientId}-ink)`}
          transform={
            diamond
              ? `translate(${AVATAR_CENTER} ${AVATAR_CENTER}) rotate(45) scale(.74) translate(${-AVATAR_CENTER} ${-AVATAR_CENTER})`
              : undefined
          }
        />
        <g fill={colorDef.eyeColor} className="lonora-shape-avatar-eyes">
          <ellipse cx={AVATAR_CENTER - 29} cy={AVATAR_CENTER - 8} rx={10} ry={7} />
          <ellipse cx={AVATAR_CENTER + 29} cy={AVATAR_CENTER - 8} rx={10} ry={7} />
        </g>
      </svg>
    </span>
  );
}

function OrganicAvatar({
  colorDef,
  identity,
  isWorking,
}: {
  colorDef: AvatarColorDef;
  identity: string;
  isWorking: boolean;
}) {
  const reducedMotion = useSyncExternalStore(
    subscribeToReducedMotion,
    reducedMotionSnapshot,
    () => false,
  );
  const seed = avatarIdentitySeed(identity || colorDef.hex);
  const shapeA = useMemo(() => organicAvatarPath(seed), [seed]);
  const shapeB = useMemo(() => organicAvatarPath(seed, 0.42), [seed]);
  const duration = `${4.8 + (seed % 24) / 10}s`;

  return (
    <svg
      viewBox="-60 -60 120 120"
      aria-hidden="true"
      className="lonora-organic-avatar"
      data-working={isWorking}
      data-shape-family={seed % 10}
      data-eye-pattern={seed % 4}
    >
      {(["idle", "working"] as const).map((mode) => (
        <path
          key={mode}
          className={`lonora-organic-avatar-body lonora-organic-avatar-body-${mode}`}
          d={shapeA}
          fill={colorDef.hex}
          style={
            {
              "--lonora-organic-path": `path("${shapeA}")`,
            } as CSSProperties
          }
        >
          {!reducedMotion ? (
            <animate
              attributeName="d"
              values={`${shapeA};${shapeB};${shapeA}`}
              dur={duration}
              repeatCount="indefinite"
            />
          ) : null}
        </path>
      ))}
      <g transform={`rotate(${(seed % 9) - 4})`}>
        {(["idle", "working"] as const).map((mode) => (
          <g key={mode} className={`lonora-organic-avatar-eyes lonora-organic-avatar-eyes-${mode}`}>
            <rect x="-14" y="-12" width="7" height="24" rx="3.5" />
            <rect x="7" y="-12" width="7" height="24" rx="3.5" />
          </g>
        ))}
      </g>
    </svg>
  );
}

const reducedMotionMedia = "(prefers-reduced-motion: reduce)";

function reducedMotionSnapshot(): boolean {
  return window.matchMedia(reducedMotionMedia).matches;
}

function subscribeToReducedMotion(onChange: () => void): () => void {
  const media = window.matchMedia(reducedMotionMedia);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
