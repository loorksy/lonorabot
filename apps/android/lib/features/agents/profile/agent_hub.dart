// The profile hub's hero: the agent's live avatar, name, role, status and the three primary
// actions, composed from the kit.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../avatar/avatar.dart';
import '../../../core/json.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';

/// The hub's dark gradients ([LnAgentPalette]), used only where one of Lonora's avatar colours maps
/// onto an agent palette (the nearest hue family of the shell colour):
///
/// | Lonora shell (`avatarPalette` id) | Agent palette | Gradient |
/// |---|---|---|
/// | `blue` #3B82F6, `cyan` #06B6D4 | Blue | #143352 → #183D62 |
/// | `red` #EF4444 | Red | #422424 → #502B2B |
/// | `yellow` #EAB308, `orange` #F97316 | Yellow | #453021 → #533A28 |
/// | `brown` #8D6E63 | Brown | #3B322B → #473C34 |
/// | `gray` #64748B, `white` #FFFFFF | Gray | #333333 → #3D3D3D |
///
/// Every other shell (violet, green, magenta, a custom hex such as the server default
/// #7c83fd) has no agent palette: the hub stays on the neutral canvas (null).
LnAgentPalette? hubGradientFor(String agentId, String? color) =>
    switch (resolveAvatarColor(agentId, color).id) {
      'blue' || 'cyan' => LnAgentPalette.blue,
      'red' => LnAgentPalette.red,
      'yellow' || 'orange' => LnAgentPalette.yellow,
      'brown' => LnAgentPalette.brown,
      'gray' || 'white' => LnAgentPalette.gray,
      _ => null,
    };

/// The agent's one status for the hub: running, paused or needing the owner.
enum HubStatus { active, working, paused, attention, degraded }

/// The status from the agent row and its live state (`GET /agents/{id}/state`).
HubStatus hubStatusOf(Agent agent, Json? live, {bool running = false}) {
  final state = live?['state'];
  if (agent.paused || state == 'paused') return HubStatus.paused;
  if (state == 'degraded') return HubStatus.degraded;
  if (state == 'action_required' ||
      live?['pending_card_id'] != null ||
      ((live?['pending_approval_count'] as num?) ?? 0) > 0 ||
      live?['phase'] == 'uncertain') {
    return HubStatus.attention;
  }
  if (running || state == 'working') return HubStatus.working;
  return HubStatus.active;
}

/// One of the hero's primary actions (Message · Call · Settings).
@immutable
class HubAction {
  const HubAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.enabled = true,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  /// Dimmed but still tappable (it explains why, e.g. calls not set up).
  final bool enabled;
}

class AgentHero extends StatelessWidget {
  const AgentHero({
    super.key,
    required this.agent,
    required this.avatarState,
    required this.status,
    required this.statusLabel,
    required this.role,
    required this.actions,
    required this.topPadding,
    this.onEditAvatar,
    this.animate = true,
  });

  final Agent agent;
  final LonoraAvatarState avatarState;
  final HubStatus status;
  final String statusLabel;
  final String role;
  final List<HubAction> actions;

  /// Room for the floating header row above the avatar.
  final double topPadding;
  final VoidCallback? onEditAvatar;
  final bool animate;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final gradient = hubGradientFor(agent.id, agent.color);
    final onHub = gradient != null;
    final ink = onHub ? LnPalette.inkWhite : c.fg;
    final mutedInk = onHub ? LnPalette.inkWhiteMuted : c.fgMuted;
    final l10n = context.l10n;

    final avatar = Semantics(
      image: true,
      label: agent.name,
      child: LonoraAvatar(
        agentId: agent.id,
        face: agent.avatar,
        color: agent.color,
        state: avatarState,
        size: 96,
        tradesOnItsOwn: agent.tradesOnItsOwn,
        animate: animate,
      ),
    );

    return Container(
      decoration: onHub
          ? BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [gradient.hubStart, gradient.hubEnd],
              ),
              borderRadius: const BorderRadius.vertical(
                bottom: Radius.circular(LnRadius.card),
              ),
            )
          : null,
      padding: EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter,
        topPadding,
        LnSpace.pageGutter,
        LnSpace.lg,
      ),
      child: Column(
        children: [
          SizedBox(
            width: 112,
            height: 104,
            child: Stack(
              alignment: Alignment.center,
              children: [
                avatar,
                if (onEditAvatar != null)
                  PositionedDirectional(
                    end: 0,
                    bottom: 0,
                    child: CircleIconButton(
                      icon: const Icon(FIcons.pencil),
                      iconSize: 16,
                      size: 32,
                      semanticLabel: l10n.t('avatarEdit'),
                      onTap: onEditAvatar,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: LnSpace.sm),
          Text(
            agent.name,
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: ln.text.largeTitle.copyWith(color: ink),
          ),
          if (role.isNotEmpty) ...[
            const SizedBox(height: LnSpace.xxs),
            Text(
              role,
              textAlign: TextAlign.center,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: ln.text.caption.copyWith(color: mutedInk),
            ),
          ],
          const SizedBox(height: LnSpace.sm),
          _StatusPill(status: status, label: statusLabel, onHub: onHub),
          const SizedBox(height: LnSpace.lg),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              for (final a in actions)
                Expanded(
                  child: _HubActionButton(action: a, onHub: onHub),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({
    required this.status,
    required this.label,
    required this.onHub,
  });

  final HubStatus status;
  final String label;
  final bool onHub;

  @override
  Widget build(BuildContext context) {
    final kind = switch (status) {
      HubStatus.active => StatusChipKind.success,
      HubStatus.working => StatusChipKind.running,
      HubStatus.paused => StatusChipKind.neutral,
      HubStatus.attention => StatusChipKind.waiting,
      HubStatus.degraded => StatusChipKind.error,
    };
    if (!onHub) {
      return Semantics(
        liveRegion: true,
        child: StatusChip(label: label, kind: kind),
      );
    }
    // On the dark hub the label is white on a translucent pill; the dot keeps its colour.
    final c = context.ln.colors;
    final dot = switch (status) {
      HubStatus.active => c.success,
      HubStatus.working => LnPalette.dark.link,
      HubStatus.paused => LnPalette.inkWhiteMuted,
      HubStatus.attention => c.pending,
      HubStatus.degraded => c.error,
    };
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsetsDirectional.fromSTEB(8, 4, 10, 4),
        decoration: BoxDecoration(
          color: c.inverseFill,
          borderRadius: const BorderRadius.all(Radius.circular(12)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
            ),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: context.ln.text.smallStrong.copyWith(
                  color: LnPalette.inkWhite,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HubActionButton extends StatelessWidget {
  const _HubActionButton({required this.action, required this.onHub});

  final HubAction action;
  final bool onHub;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final ink = onHub ? LnPalette.inkWhite : c.fg;
    final circle = Container(
      width: 52,
      height: 52,
      alignment: Alignment.center,
      decoration: onHub
          // 12 % white on the hub's dark gradient: no kit token for this fill.
          ? const BoxDecoration(
              color: Color(0x1FFFFFFF),
              shape: BoxShape.circle,
            )
          : BoxDecoration(
              color: c.surface,
              shape: BoxShape.circle,
              border: Border.all(color: c.border),
              boxShadow: ln.chromeShadow,
            ),
      child: Icon(action.icon, size: LnSize.chromeIcon, color: ink),
    );
    return LnTappable(
      onTap: action.onTap,
      haptic: true,
      semanticLabel: action.label,
      excludeChildSemantics: true,
      child: Opacity(
        opacity: action.enabled ? 1 : 0.4,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 48),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              circle,
              const SizedBox(height: 6),
              Text(
                action.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: ln.text.footnote.copyWith(color: ink),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
