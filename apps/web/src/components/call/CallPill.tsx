import { t } from "@lingui/core/macro";
import { avatarState } from "@lonora/core";
import { AgentAvatar } from "@lonora/ui-web";
import { ChevronDown, MicOff } from "lucide-react";
import { useVoice } from "../../hooks/useVoice";
import { CallWaveform } from "./CallWaveform";
export function CallPill() {
  const voice = useVoice();
  if (!voice.target || !voice.minimized) return null;
  const { name, color, avatar } = voice.target;
  return (
    <button
      type="button"
      className="call-header-pill"
      aria-label={t`Open call with ${name}`}
      onClick={voice.expand}
      data-testid="active-call-pill"
    >
      <span className="call-mini-avatar">
        <AgentAvatar
          name={name}
          shape={avatar}
          superBot={voice.target?.super_bot_active}
          superBotLabel={t`Super Bot enabled`}
          color={color}
          working={voice.phase === "speaking" && voice.connected}
          state={avatarState({ voice, error: voice.error != null })}
        />
      </span>
      <CallWaveform meter={voice.meter} compact />
      {voice.muted ? <MicOff size={13} /> : null}
      <ChevronDown size={13} />
    </button>
  );
}
