/** The reference's `springTo`: a damped spring from the finger's own velocity, never overshooting its target. */
export type Spring = { k: number; z: number };

export function springTo({
  from,
  to,
  v = 0,
  k = 380,
  z = 1,
  onFrame,
  onDone,
}: Spring & {
  from: number;
  to: number;
  v?: number;
  onFrame: (x: number, v: number) => void;
  onDone?: () => void;
}) {
  const c = 2 * z * Math.sqrt(k);
  const dir = Math.sign(to - from);
  let x = from;
  let vel = v;
  let last = performance.now();
  let raf = 0;
  const tick = (now: number) => {
    const dt = Math.min(0.034, Math.max(0.001, (now - last) / 1000));
    last = now;
    for (let i = 0; i < 4; i++) {
      const h = dt / 4;
      const a = -k * (x - to) - c * vel;
      vel += a * h;
      x += vel * h;
    }
    if (dir && (to - x) * dir < 0) {
      x = to;
      vel = 0;
    }
    onFrame(x, vel);
    if (Math.abs(x - to) < 0.35 && Math.abs(vel) < 24) {
      raf = 0;
      onFrame(to, 0);
      onDone?.();
      return;
    }
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return {
    stop() {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    },
    get running() {
      return raf !== 0;
    },
  };
}
export type SpringHandle = ReturnType<typeof springTo>;

/** Rubber band past the first or last page. */
export const rubber = (x: number, width: number) => {
  const d = width * 0.5;
  return Math.sign(x) * (1 - 1 / ((Math.abs(x) * 0.55) / d + 1)) * d;
};

/** A quick tick where a gesture changes its mind; silent where the device cannot vibrate. */
export function haptic(pattern: number | number[]) {
  navigator.vibrate?.(pattern);
}
