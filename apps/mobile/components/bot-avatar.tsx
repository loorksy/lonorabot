import {
  AvatarMotion,
  type AvatarStateId,
  avatarBarPath,
  avatarPersonality,
  avatarState,
  avatarTurn,
  FACE_TOKENS,
  faceTransform,
  GEOMETRY,
  GLYPH_SCALE,
  idleAvatarPose,
  resolveAvatarColor,
  resolveAvatarFace,
} from "@lonora/core";
import { memo, useEffect, useId, useMemo, useRef, useState } from "react";
import { AppState, View } from "react-native";
import { useReducedMotion } from "react-native-reanimated";
import Svg, {
  Circle,
  ClipPath,
  Defs,
  Ellipse,
  FeColorMatrix,
  FeGaussianBlur,
  FeMerge,
  FeMergeNode,
  Filter,
  G,
  Path,
  RadialGradient,
  Rect,
  Stop,
} from "react-native-svg";
import { useSession } from "../lib/session";
import { colors } from "./ui";

/** Native SVG renderer with shared signal geometry and interactive spherical idle motion. */
export const BotAvatar = memo(function BotAvatar({
  color,
  size = 54,
  working = false,
  identity = "",
  superBot = false,
  state,
  variant = "orb",
  paused = false,
}: {
  color: string;
  size?: number;
  working?: boolean;
  variant?: string;
  identity?: string;
  superBot?: boolean;
  state?: AvatarStateId;
  paused?: boolean;
}) {
  const { t } = useSession();
  const id = `mta${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const motionIdentity = identity || id;
  const profile = useMemo(() => avatarPersonality(motionIdentity), [motionIdentity]);
  const visualState = state ?? avatarState({ working });
  const faceId = resolveAvatarFace(variant);
  const [sampler] = useState(() => new AvatarMotion(visualState, motionIdentity, faceId));
  const motion = useRef(sampler);
  const [bars, setBars] = useState(() => motion.current.frame(0));
  const reduced = useReducedMotion();
  const [poke, setPoke] = useState(0);
  const [foreground, setForeground] = useState(
    AppState.currentState !== "background" && AppState.currentState !== "inactive",
  );
  const elapsed = useRef(0);
  const idleEpoch = useRef(0);
  const tapSpin = useRef<number | null>(null);
  const pointer = useRef<{ x: number; y: number; until: number } | null>(null);
  const [pose, setPose] = useState({ gazeX: 0, gazeY: 0, yaw: 0 });
  useEffect(() => {
    const listener = AppState.addEventListener("change", (next) =>
      setForeground(next === "active"),
    );
    return () => listener.remove();
  }, []);
  useEffect(() => {
    motion.current.setFace(faceId);
    setBars(motion.current.frame(0, reduced || paused));
  }, [faceId, reduced, paused]);
  useEffect(() => {
    motion.current.setIdentity(motionIdentity);
    motion.current.setState(visualState);
    idleEpoch.current = elapsed.current;
    tapSpin.current = null;
    setBars(motion.current.frame(0, reduced || paused));
    if (reduced || paused || !foreground) return;
    let frame = 0;
    let previous = 0;
    const draw = (now: number) => {
      if (!previous || now - previous >= 1000 / 30) {
        const dt = previous ? Math.min((now - previous) / 1000, 0.1) : 0;
        elapsed.current += dt;
        setBars(motion.current.frame(dt));
        const idle =
          visualState === "waiting"
            ? idleAvatarPose(elapsed.current - idleEpoch.current, motionIdentity)
            : { gazeX: Math.sin(now / 2400) * 0.4, gazeY: 0, yaw: 0 };
        let yaw = idle.yaw;
        if (visualState === "waiting" && tapSpin.current !== null) {
          const progress = Math.min(1, (elapsed.current - tapSpin.current) / profile.spinSeconds);
          yaw = profile.direction * Math.PI * 2 * (progress * progress * (3 - 2 * progress));
          if (progress >= 1) {
            tapSpin.current = null;
            // Start the next idle cycle facing forward after a manually requested turn.
            idleEpoch.current = elapsed.current;
          }
        }
        const target = pointer.current;
        setPose({
          gazeX: target && elapsed.current < target.until ? target.x : idle.gazeX,
          gazeY: target && elapsed.current < target.until ? target.y : idle.gazeY,
          yaw,
        });
        setPoke((value) => (value < 0.005 ? 0 : value * Math.exp(-dt * 12)));
        previous = now;
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [visualState, reduced, paused, foreground, motionIdentity, profile]);
  const aim = (event: {
    nativeEvent: { locationX?: number; locationY?: number; offsetX?: number; offsetY?: number };
  }) => {
    if (reduced || paused) return;
    const { locationX, locationY, offsetX, offsetY } = event.nativeEvent;
    const x = locationX ?? offsetX;
    const y = locationY ?? offsetY;
    if (typeof x === "number" && typeof y === "number") {
      pointer.current = {
        x: Math.max(-1, Math.min(1, (x / size - 0.5) * 2)),
        y: Math.max(-0.8, Math.min(0.8, (y / size - 0.5) * 1.6)),
        until: elapsed.current + 1.5,
      };
    }
  };
  const react = (event: Parameters<typeof aim>[0]) => {
    if (reduced || paused) return;
    aim(event);
    setPoke(0.8);
    if (visualState === "waiting") tapSpin.current = elapsed.current;
  };
  const facial = visualState === "waiting" && faceId !== "orb";
  const face = GEOMETRY.face;
  const look = faceTransform(
    reduced || paused ? 0 : pose.gazeX,
    reduced || paused ? 0 : pose.gazeY,
    reduced || paused ? 0 : poke,
  );
  const turn = avatarTurn(reduced || paused || visualState !== "waiting" ? 0 : pose.yaw);
  const turnTransform = `translate(${200 + turn.tx} 200.5) scale(${turn.scaleX} 1) translate(-200 -200.5)`;
  const transform = `translate(${200 + look.tx} ${200.5 + look.ty}) rotate(${look.rot}) skewY(${look.skew}) scale(${look.sx} ${look.sy}) translate(-200 -200.5)`;
  return (
    <View
      testID="trading-avatar"
      nativeID={`${id}-motion-${motionIdentity}`}
      style={{ width: size, height: size }}
      onTouchStart={react}
      onTouchMove={aim}
      onPointerDown={react}
      onPointerMove={aim}
    >
      <Svg
        width={size}
        height={size}
        viewBox={GEOMETRY.viewBox}
        preserveAspectRatio="xMidYMid meet"
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
      >
        <Defs>
          <ClipPath id={`${id}clip`}>
            <Rect {...face} />
          </ClipPath>
          <ClipPath id={`${id}sphere`}>
            <Circle {...GEOMETRY.shell} />
          </ClipPath>
          <RadialGradient id={`${id}shade`} cx="34%" cy="27%" r="95%">
            <Stop offset="0" stopColor="#fff" stopOpacity={0.4} />
            <Stop offset="0.38" stopColor="#fff" stopOpacity={0} />
            <Stop offset="0.6" stopColor="#000" stopOpacity={0} />
            <Stop offset="1" stopColor="#000" stopOpacity={0.42} />
          </RadialGradient>
          <RadialGradient id={`${id}gloss`}>
            <Stop offset="0" stopColor="#fff" stopOpacity={0.5} />
            <Stop offset="1" stopColor="#fff" stopOpacity={0} />
          </RadialGradient>
          <Filter
            id={`${id}goo`}
            filterUnits="userSpaceOnUse"
            x={face.x}
            y={face.y}
            width={face.width}
            height={face.height}
          >
            <FeGaussianBlur
              in="SourceGraphic"
              stdDeviation={facial ? FACE_TOKENS.render.gooBlur : 1.65}
              result="b"
            />
            <FeColorMatrix
              in="b"
              type="matrix"
              values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 20 -9.5"
              result="g"
            />
            <FeGaussianBlur
              in="g"
              stdDeviation={facial ? FACE_TOKENS.render.glowBlur : 5}
              result="glowSource"
            />
            <FeColorMatrix
              in="glowSource"
              type="matrix"
              values={`1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 ${facial ? FACE_TOKENS.render.glowOpacity : 1} 0`}
              result="glow"
            />
            <FeMerge>
              <FeMergeNode in="glow" />
              <FeMergeNode in="g" />
            </FeMerge>
          </Filter>
        </Defs>
        <Circle {...GEOMETRY.shell} fill={resolveAvatarColor(identity, color).hex} />
        <Circle {...GEOMETRY.shell} fill={`url(#${id}shade)`} />
        <G clipPath={`url(#${id}sphere)`}>
          <G id={`${id}turn`} transform={turnTransform} opacity={turn.opacity}>
            <G transform={transform}>
              <Rect {...face} fill="#0d0d11" />
              <G clipPath={`url(#${id}clip)`}>
                <G filter={size >= 48 ? `url(#${id}goo)` : undefined}>
                  {bars.map((bar, i) => (
                    <Path
                      // biome-ignore lint/suspicious/noArrayIndexKey: fixed particle slots never reorder.
                      key={i}
                      d={avatarBarPath(bar)}
                      fill="none"
                      stroke={`rgb(${Math.round(bar.r)},${Math.round(bar.g)},${Math.round(bar.b)})`}
                      strokeWidth={Math.max(bar.w * GLYPH_SCALE, 0.01)}
                      opacity={bar.o}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  ))}
                </G>
              </G>
            </G>
          </G>
        </G>
        <Ellipse
          cx={150}
          cy={82}
          rx={86}
          ry={38}
          transform="rotate(-24 150 82)"
          fill={`url(#${id}gloss)`}
          opacity={0.55}
        />
      </Svg>
      {superBot && (
        <View
          testID="super-bot-avatar"
          accessible
          accessibilityLabel={t("superBotEnabled")}
          pointerEvents="none"
          style={{
            position: "absolute",
            inset: -3,
            borderRadius: size,
            borderWidth: 2,
            borderColor: "#f0c866",
          }}
        >
          <Svg
            width={Math.max(12, size * 0.34)}
            height={Math.max(12, size * 0.34)}
            viewBox="0 0 20 20"
            style={{ position: "absolute", right: -3, top: -4 }}
          >
            <Circle cx={10} cy={10} r={10} fill={colors.background} />
            <Path d="M4 7 7 9 10 4 13 9 16 7 14 14H6Z" fill="#f0c866" />
          </Svg>
        </View>
      )}
    </View>
  );
});
