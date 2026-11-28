// The heads-up banner: the kit's top toast (an inverse-surface stadium, with a warning-colour disc
// for items that need the owner) carrying Lonora's heads-up content
// (apps/mobile/components/heads-up.tsx): the conversation's avatar and name, «{speaker}:» and the
// words, and «رد». Tap opens the conversation (a broker health problem: «التعطل والاستعادة», its
// button reading that name), swipe up dismisses, press holds.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/app_state.dart';
import '../navigation.dart';
import 'heads_up_controller.dart';
import 'heads_up_rules.dart';

/// What a banner says to a screen reader: «name: speaker words».
String headsUpLabel(String title, String? who, String text) =>
    '$title: ${who == null ? '' : '$who '}$text';

/// The banner's look: one row on the toast surface.
class HeadsUpBannerView extends StatelessWidget {
  const HeadsUpBannerView({
    super.key,
    required this.title,
    required this.text,
    required this.avatar,
    this.who,
    this.kind = HeadsUpKind.message,
    this.onOpen,
    this.onHold,
    this.actionLabel,
  });

  final String title;
  final String text;
  final String? who;
  final Widget avatar;
  final HeadsUpKind kind;

  /// The button's word; «رد» by default.
  final String? actionLabel;
  final VoidCallback? onOpen;
  final ValueChanged<bool>? onHold;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final line = ln.text.footnote.copyWith(color: c.onInverseMuted);
    final reply = actionLabel ?? context.t('reply');
    final label = headsUpLabel(title, who, text);
    // Not a live region: the layer announces each banner once (TalkBack would read it twice).
    return Semantics(
      container: true,
      child: Container(
        decoration: BoxDecoration(
          color: c.inverseSurface,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.card)),
          boxShadow: LnShadow.darkChrome,
        ),
        padding: const EdgeInsetsDirectional.fromSTEB(12, 10, 6, 10),
        child: Row(
          children: [
            Expanded(
              child: _Press(
                label: label,
                onTap: onOpen,
                onHold: onHold,
                child: Row(
                  children: [
                    SizedBox.square(
                      dimension: 40,
                      child: Stack(
                        clipBehavior: Clip.none,
                        children: [
                          Positioned.fill(child: avatar),
                          if (kind == HeadsUpKind.attention)
                            PositionedDirectional(
                              end: -2,
                              bottom: -2,
                              child: Container(
                                width: 18,
                                height: 18,
                                decoration: BoxDecoration(
                                  color: c.warning,
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: c.inverseSurface,
                                    width: 2,
                                  ),
                                ),
                                alignment: Alignment.center,
                                child: Icon(
                                  FIcons.info,
                                  size: 11,
                                  color: c.onAccent,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(width: LnSpace.sm),
                    Expanded(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: ln.text.captionStrong.copyWith(
                              color: c.onInverse,
                            ),
                          ),
                          // The speaker leads in the interface's direction; the words are
                          // isolated so they read in their own direction (as the chat row).
                          Text.rich(
                            TextSpan(
                              children: [
                                if (who != null)
                                  TextSpan(
                                    text: '${isolate(who!)} ',
                                    style: line.copyWith(
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                // First-strong isolate; the line's own number isolates stay.
                                TextSpan(text: '\u2068$text\u2069'),
                              ],
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.start,
                            style: line,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            _Press(
              label: reply,
              onTap: onOpen,
              onHold: onHold,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    child: Text(
                      reply,
                      style: ln.text.captionStrong.copyWith(
                        color: c.toastAction,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Press feedback (opacity 0.4) that also reports the hold.
class _Press extends StatefulWidget {
  const _Press({
    required this.label,
    required this.child,
    this.onTap,
    this.onHold,
  });

  final String label;
  final Widget child;
  final VoidCallback? onTap;
  final ValueChanged<bool>? onHold;

  @override
  State<_Press> createState() => _PressState();
}

class _PressState extends State<_Press> {
  bool _down = false;

  void _set(bool down) {
    if (_down == down) return;
    setState(() => _down = down);
    widget.onHold?.call(down);
  }

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: widget.label,
    excludeSemantics: true,
    onTap: widget.onTap,
    child: GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) => _set(true),
      onTapUp: (_) => _set(false),
      onTapCancel: () => _set(false),
      onTap: widget.onTap,
      child: AnimatedOpacity(
        opacity: _down ? LnMotion.pressOpacity : 1,
        duration: _down ? LnMotion.pressDown : LnMotion.pressUp,
        child: widget.child,
      ),
    ),
  );
}

/// The conversation's avatar: the agent's, or the group's members.
class HeadsUpAvatar extends StatelessWidget {
  const HeadsUpAvatar({super.key, this.agent, this.group, this.agents});

  final Agent? agent;
  final Group? group;
  final Map<String, Agent>? agents;

  @override
  Widget build(BuildContext context) {
    final a = agent;
    if (a != null) {
      return LonoraAvatar(
        agentId: a.id,
        face: a.avatar,
        color: a.color,
        tradesOnItsOwn: a.tradesOnItsOwn,
        size: 40,
        animate: false,
      );
    }
    final members = [
      for (final id in group?.memberIds ?? const <String>[])
        if (agents?[id] case final Agent m)
          LonoraAvatarMember(
            agentId: m.id,
            face: m.avatar,
            color: m.color,
            tradesOnItsOwn: m.tradesOnItsOwn,
          ),
    ];
    return LonoraGroupAvatar(members: members, size: 40, animate: false);
  }
}

/// The banner layer of [PlatformOverlayHost]: slides the current banner in at the top.
class HeadsUpLayer extends StatefulWidget {
  const HeadsUpLayer({super.key, required this.controller});

  final HeadsUpController controller;

  @override
  State<HeadsUpLayer> createState() => _HeadsUpLayerState();
}

class _HeadsUpLayerState extends State<HeadsUpLayer> {
  ShownBanner? _shown;
  bool _visible = false;
  double _drag = 0;

  /// What the shown banner says («name: words»), for the announcement.
  String? _label;

  @override
  void initState() {
    super.initState();
    widget.controller.current.addListener(_onChange);
    // A banner already up when the layer is (re)mounted is shown, not announced again.
    final current = widget.controller.current.value;
    if (current != null) {
      _shown = current;
      _visible = true;
    }
  }

  @override
  void dispose() {
    widget.controller.current.removeListener(_onChange);
    super.dispose();
  }

  void _onChange() {
    final next = widget.controller.current.value;
    if (next != null) {
      setState(() {
        _shown = next;
        _visible = true;
        _drag = 0;
      });
      // Once built, with the conversation's name.
      WidgetsBinding.instance.addPostFrameCallback((_) => _announce(next));
    } else if (_visible) {
      setState(() => _visible = false);
    }
  }

  void _announce(ShownBanner shown) {
    if (!mounted || _shown?.serial != shown.serial) return;
    final label = _label;
    final view = View.maybeOf(context);
    if (label == null || view == null) return;
    SemanticsService.sendAnnouncement(view, label, Directionality.of(context));
  }

  void _open(HeadsUpBanner banner) {
    widget.controller.dismiss();
    PlatformNavigation.open(
      banner.location ?? Routes.thread(banner.threadId, around: banner.around),
    );
  }

  @override
  Widget build(BuildContext context) {
    final shown = _shown;
    if (shown == null) return const SizedBox.shrink();
    final banner = shown.banner;
    final shell = context.getSelect<AppState, ShellState>((s) => s.shell);
    final agent = banner.groupId == null ? shell.agents[banner.agentId] : null;
    final group = banner.groupId == null ? null : shell.groups[banner.groupId];
    final title = group?.name ?? agent?.name ?? 'Lonora';
    _label = headsUpLabel(title, banner.who, banner.text);
    final top = MediaQuery.paddingOf(context).top + LnSpace.xs;
    return PositionedDirectional(
      top: top,
      start: LnSpace.pageGutter,
      end: LnSpace.pageGutter,
      child: GestureDetector(
        onVerticalDragUpdate: (d) =>
            setState(() => _drag = (_drag + d.delta.dy).clamp(-160.0, 12.0)),
        onVerticalDragEnd: (_) {
          if (_drag < -24) {
            widget.controller.dismiss();
          } else {
            setState(() => _drag = 0);
          }
        },
        child: AnimatedSlide(
          offset: _visible ? Offset.zero : const Offset(0, -1.6),
          duration: _visible ? LnMotion.slow : LnMotion.medium,
          curve: _visible ? LnMotion.emphasized : LnMotion.standard,
          onEnd: () {
            if (!_visible && mounted) setState(() => _shown = null);
          },
          child: Transform.translate(
            offset: Offset(0, _drag),
            child: KeyedSubtree(
              key: ValueKey(shown.serial),
              child: HeadsUpBannerView(
                title: title,
                who: banner.who,
                text: banner.text,
                kind: banner.kind,
                avatar: HeadsUpAvatar(
                  agent: agent,
                  group: group,
                  agents: shell.agents,
                ),
                onOpen: () => _open(banner),
                onHold: widget.controller.hold,
                actionLabel: banner.location == null
                    ? null
                    : context.t('rc_title'),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
