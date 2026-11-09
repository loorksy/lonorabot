/** The brand mark (3D bars) of the reference; its gradients are brand art, not tokens. */
export function LogoMark({ size = 40 }: { size?: number }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <linearGradient id="lm-ivory" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#cfd1d8" />
        </linearGradient>
        <linearGradient id="lm-ink" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2a2c33" />
          <stop offset="1" stopColor="#0b0c10" />
        </linearGradient>
        <linearGradient id="lm-accent" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#6ff5cd" />
          <stop offset="1" stopColor="#14b986" />
        </linearGradient>
        <filter id="lm-glow" x="-60%" y="-30%" width="220%" height="160%">
          <feGaussianBlur stdDeviation="3" />
        </filter>
      </defs>
      <rect className="lb" x="5" y="33" width="11" height="19" rx="5.5" />
      <rect className="lb" x="19" y="24" width="11" height="28" rx="5.5" />
      <rect
        x="33"
        y="10"
        width="12"
        height="42"
        rx="6"
        fill="#22E3A8"
        opacity=".55"
        filter="url(#lm-glow)"
      />
      <rect x="33" y="10" width="12" height="42" rx="6" fill="url(#lm-accent)" />
      <rect className="lb" x="48" y="29" width="11" height="23" rx="5.5" />
    </svg>
  );
}
