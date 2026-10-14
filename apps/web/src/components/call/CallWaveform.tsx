// biome-ignore-all lint/suspicious/noArrayIndexKey: Waveform bars have fixed sample-position identity, no child state.
// Bars are historical amplitudes from this call's actual microphone/remote WebRTC streams.
import { useVoiceLevels, type VoiceMeter } from "../../hooks/useVoice";
export function CallWaveform({ meter, compact = false }: { meter: VoiceMeter; compact?: boolean }) {
  const levels = useVoiceLevels(meter);
  return (
    <span className={compact ? "call-waveform compact" : "call-waveform"} aria-hidden="true">
      {levels.slice(compact ? -8 : 0).map((level, index) => (
        <span key={`sample-${index}`} style={{ height: `${3 + level * (compact ? 15 : 30)}px` }} />
      ))}
    </span>
  );
}
