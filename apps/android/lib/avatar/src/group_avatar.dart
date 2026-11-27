// Group avatar: port of apps/mobile/components/group-avatar.tsx (cluster) plus a list-row layout of
// two 28 dp avatars side by side.
import 'dart:math' as math;

import 'package:flutter/material.dart' show Icons, Theme;
import 'package:flutter/widgets.dart';

import '../../design/tokens.dart';
import 'avatar_state.dart';
import 'lonora_avatar.dart';

/// What a group avatar needs from each member agent.
@immutable
class LonoraAvatarMember {
  const LonoraAvatarMember({
    required this.agentId,
    this.face,
    this.color,
    this.tradesOnItsOwn = false,
    this.state = LonoraAvatarState.idle,
  });

  final String agentId;
  final String? face;
  final String? color;
  final bool tradesOnItsOwn;
  final LonoraAvatarState state;
}

enum LonoraGroupAvatarLayout {
  /// Up to three overlapping members inside a [LonoraGroupAvatar.size] circle; four or
  /// more show two members and a "+N" disc (group-avatar.tsx).
  cluster,

  /// The first two members side by side, each [LonoraGroupAvatar.size] wide, overlapping
  /// by 1 dp (2 × 28 dp = 55 dp in list rows).
  pair,
}

class LonoraGroupAvatar extends StatelessWidget {
  /// The cluster of group-avatar.tsx; [size] is the whole avatar.
  const LonoraGroupAvatar({
    super.key,
    required this.members,
    this.size = 54,
    this.animate = true,
    this.palette,
  }) : layout = LonoraGroupAvatarLayout.cluster;

  /// Two avatars side by side for list rows; [size] is each avatar.
  const LonoraGroupAvatar.pair({
    super.key,
    required this.members,
    this.size = LnSize.avatarGroup,
    this.animate = true,
    this.palette,
  }) : layout = LonoraGroupAvatarLayout.pair;

  final List<LonoraAvatarMember> members;
  final double size;
  final LonoraGroupAvatarLayout layout;
  final bool animate;

  /// Colours of the empty disc and the "+N" badge; defaults follow the theme brightness.
  final LnPalette? palette;

  @override
  Widget build(BuildContext context) {
    final colors =
        palette ??
        (Theme.of(context).brightness == Brightness.dark
            ? LnPalette.dark
            : LnPalette.light);
    if (members.isEmpty) return _disc(colors, size, null);
    if (members.length == 1) return _avatar(members.first, size);
    if (layout == LonoraGroupAvatarLayout.pair) {
      return SizedBox(
        width: size * 2 - 1,
        height: size,
        child: Stack(
          children: [
            PositionedDirectional(
              start: 0,
              top: 0,
              child: _avatar(members[0], size),
            ),
            PositionedDirectional(
              start: size - 1,
              top: 0,
              child: _avatar(members[1], size),
            ),
          ],
        ),
      );
    }
    final pair = members.length == 2;
    final mini = (size * (pair ? 0.65 : 0.54)).roundToDouble();
    final slots = pair
        ? [(left: 0.0, top: 0.0), (left: size - mini, top: size - mini)]
        : [
            (left: (size - mini) / 2, top: 0.0),
            (left: 0.0, top: size - mini),
            (left: size - mini, top: size - mini),
          ];
    final shown = members.take(members.length > 3 ? 2 : 3).toList();
    return SizedBox.square(
      dimension: size,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          for (var i = 0; i < shown.length; i++)
            Positioned(
              left: slots[i].left,
              top: slots[i].top,
              child: _avatar(shown[i], mini),
            ),
          if (members.length > 3)
            Positioned(
              left: size - mini,
              top: size - mini,
              child: _disc(colors, mini, '+${members.length - 2}'),
            ),
        ],
      ),
    );
  }

  Widget _avatar(LonoraAvatarMember member, double dimension) => LonoraAvatar(
    key: ValueKey(member.agentId),
    agentId: member.agentId,
    face: member.face,
    color: member.color,
    state: member.state,
    tradesOnItsOwn: member.tradesOnItsOwn,
    size: dimension,
    animate: animate,
  );

  Widget _disc(LnPalette colors, double dimension, String? count) => Container(
    width: dimension,
    height: dimension,
    alignment: Alignment.center,
    decoration: BoxDecoration(color: colors.fill4, shape: BoxShape.circle),
    child: count == null
        ? Icon(
            Icons.group_outlined,
            size: dimension * 0.4,
            color: colors.fgMuted,
          )
        : Text(
            count,
            maxLines: 1,
            style: TextStyle(
              color: colors.fg,
              fontSize: math.min(11, dimension * 0.4),
            ),
          ),
  );
}
