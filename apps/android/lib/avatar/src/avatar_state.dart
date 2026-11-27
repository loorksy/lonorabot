// Avatar state ids and their derivation from observed activity.
//
// Ports packages/core/src/avatar-state.ts (whole file), the phase → avatar table of
// packages/core/src/turn-activity.ts:134-150 and liveAvatarState from
// packages/core/src/agent-status.ts:206-217.

/// The twenty glyph states of the avatar (`STATE_IDS`, trading-avatar-motion.js:40-61).
///
/// [waiting] is the resting identity (four signal bars, or the chosen face). It is also
/// reachable as [idle].
enum LonoraAvatarState {
  thinking,
  executing,
  inspecting,
  writing,
  searching,
  working,
  listening,
  reviewing,
  waiting,
  angry,
  sending,
  speaking,
  success,
  error,
  warning,
  analyzing,
  learning,
  sleeping,
  celebrating,
  connecting;

  /// The resting state (the wire id is `waiting`).
  static const LonoraAvatarState idle = waiting;

  /// Wire id, identical to the JavaScript `AvatarStateId`.
  String get id => name;

  /// Unknown or missing ids rest ([waiting]), as the web controller does.
  static LonoraAvatarState fromId(String? id) {
    for (final state in values) {
      if (state.name == id) return state;
    }
    return waiting;
  }
}

/// Voice-call transport as seen by the avatar (avatar-state.ts:11).
class AvatarVoice {
  const AvatarVoice({
    required this.connected,
    required this.speaking,
    required this.muted,
    this.ending = false,
  });

  final bool connected;

  /// `phase === "speaking"`; otherwise the call is listening.
  final bool speaking;
  final bool muted;
  final bool ending;
}

/// Visual state is a projection of observed activity, never a simulated job sequence
/// (avatar-state.ts:4-24).
LonoraAvatarState avatarStateFor({
  bool working = false,
  bool waiting = false,
  bool error = false,
  AvatarVoice? voice,
}) {
  if (error) return LonoraAvatarState.error;
  if (voice != null) {
    if (voice.ending) return LonoraAvatarState.waiting;
    if (!voice.connected) return LonoraAvatarState.connecting;
    if (voice.speaking) return LonoraAvatarState.speaking;
    return voice.muted
        ? LonoraAvatarState.waiting
        : LonoraAvatarState.listening;
  }
  if (waiting) return LonoraAvatarState.reviewing;
  return working ? LonoraAvatarState.working : LonoraAvatarState.waiting;
}

/// Run activity phase (`ActivityPhase`) → avatar, turn-activity.ts:134-150.
const Map<String, LonoraAvatarState> activityPhaseAvatar = {
  'queued': LonoraAvatarState.waiting,
  'preparing': LonoraAvatarState.thinking,
  'thinking': LonoraAvatarState.thinking,
  'searching': LonoraAvatarState.searching,
  'reading': LonoraAvatarState.inspecting,
  'analyzing': LonoraAvatarState.analyzing,
  'executing': LonoraAvatarState.executing,
  'learning': LonoraAvatarState.learning,
  'sending': LonoraAvatarState.sending,
  'writing': LonoraAvatarState.writing,
  'waiting_input': LonoraAvatarState.reviewing,
  'waiting_external': LonoraAvatarState.reviewing,
  'completed': LonoraAvatarState.success,
  'failed': LonoraAvatarState.error,
  'cancelled': LonoraAvatarState.waiting,
};

/// Between runs the avatar follows the server's live phase (agent-status.ts:206-217):
/// paused → sleeping, degraded/action_required → warning, working → working,
/// monitoring → inspecting, otherwise waiting. Pass `AgentLiveState.state` / `.phase`.
LonoraAvatarState liveAvatarState({String? state, String? phase}) {
  if (state == null) return LonoraAvatarState.waiting;
  if (state == 'paused') return LonoraAvatarState.sleeping;
  if (state == 'degraded' || state == 'action_required') {
    return LonoraAvatarState.warning;
  }
  if (state == 'working') return LonoraAvatarState.working;
  if (phase == 'monitoring') return LonoraAvatarState.inspecting;
  return LonoraAvatarState.waiting;
}
