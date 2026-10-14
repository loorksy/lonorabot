import { Trans } from "@lingui/react/macro";
export function VoiceStatus({
  connected,
  busy,
  phase = "listening",
  muted = false,
  ending = false,
}: {
  connected: boolean;
  busy: boolean;
  phase?: "listening" | "speaking";
  muted?: boolean;
  ending?: boolean;
}) {
  return (
    <span role="status" className="call-status">
      {ending ? (
        <Trans>Ending call</Trans>
      ) : !connected ? (
        busy ? (
          <Trans>Connecting</Trans>
        ) : (
          <Trans>Call ended</Trans>
        )
      ) : phase === "speaking" ? (
        <Trans>Speaking</Trans>
      ) : muted ? (
        <Trans>Microphone muted</Trans>
      ) : (
        <Trans>Listening</Trans>
      )}
    </span>
  );
}
