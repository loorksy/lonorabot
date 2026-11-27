// The profile hub's hero: the agent's live avatar, name, role, status and the three primary
// actions, composed from the kit. It has no surface of its own: it sits on the profile page's
// screen-fixed gradient ([LnPalette.profileTop] → [LnPalette.profileBottom]).
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../avatar/avatar.dart';
import '../../../core/json.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';

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

  /// The avatar's size (80 dp, the profile's identity size).
  static const double avatarSize = 80;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;

    final avatar = Semantics(
      image: true,
      label: agent.name,
      child: LonoraAvatar(
        agentId: agent.id,
        face: agent.avatar,
        color: agent.color,
        state: avatarState,
        size: avatarSize,
        tradesOnItsOwn: agent.tradesOnItsOwn,
        animate: animate,
      ),
    );

    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        LnSpace.pageGutter,
        topPadding,
        LnSpace.pageGutter,
        LnSpace.lg,
      ),
      child: Column(
        children: [
          // The pencil's 48 dp touch box sits on the avatar's bottom-end edge.
          SizedBox(
            width: avatarSize + 24,
            height: avatarSize + 12,
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
          Semantics(
            header: true,
            child: Text(
              agent.name,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: ln.text.display.copyWith(color: c.fg),
            ),
          ),
          if (role.isNotEmpty) ...[
            const SizedBox(height: LnSpace.xxs),
            Text(
              role,
              textAlign: TextAlign.center,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: ln.text.caption.copyWith(color: c.fgMuted),
            ),
          ],
          const SizedBox(height: LnSpace.sm),
          _StatusPill(status: status, label: statusLabel),
          const SizedBox(height: LnSpace.lg),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              for (final a in actions)
                Expanded(child: _HubActionButton(action: a)),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status, required this.label});

  final HubStatus status;
  final String label;

  @override
  Widget build(BuildContext context) {
    final kind = switch (status) {
      HubStatus.active => StatusChipKind.success,
      HubStatus.working => StatusChipKind.running,
      HubStatus.paused => StatusChipKind.neutral,
      HubStatus.attention => StatusChipKind.waiting,
      HubStatus.degraded => StatusChipKind.error,
    };
    return Semantics(
      liveRegion: true,
      child: StatusChip(label: label, kind: kind),
    );
  }
}

class _HubActionButton extends StatelessWidget {
  const _HubActionButton({required this.action});

  final HubAction action;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    // On the profile gradient: a 7 % ink lift in dark (the page's own controls read one step
    // above the gradient), the white chrome circle with its rim and shadow in light.
    final circle = Container(
      width: 52,
      height: 52,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: c.isDark ? c.fill4 : c.chromeCircle,
        shape: BoxShape.circle,
        border: Border.fromBorderSide(ln.chromeRim),
        boxShadow: c.isDark ? null : ln.chromeShadow,
      ),
      child: Icon(action.icon, size: LnSize.chromeIcon, color: c.fg),
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
                style: ln.text.footnote.copyWith(color: c.fg),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
