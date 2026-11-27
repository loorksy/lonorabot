// Conversation header: Ø44 circles at the 16 dp gutter — back at the start, the conversation's
// actions at the end — around the centred avatar + name capsule, which opens the agent's profile or
// the group's settings. The actions menu carries Lonora's thread menu (apps/mobile/app/thread.tsx
// ActionMenu): call the agent, charts, routines, files, chat experience, agent/group settings.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../avatar/avatar.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/prefs_actions.dart';
import '../../state/app_state.dart';
import '../voice/voice_api.dart';

/// Height from the screen top to the first message (22 dp under the capsule).
double conversationHeaderExtent(BuildContext context) =>
    MediaQuery.paddingOf(context).top +
    ScreenHeader.topGapDefault -
    2 +
    2 +
    TitleCapsule.height +
    22;

class ConversationHeader extends StatelessWidget {
  const ConversationHeader({
    super.key,
    required this.threadId,
    required this.title,
    this.agent,
    this.group,
    this.members = const [],
    this.avatarState = LonoraAvatarState.idle,
    this.callable = false,
  });

  final String threadId;
  final String title;
  final Agent? agent;
  final Group? group;

  /// The group's member agents (group avatar).
  final List<Agent> members;
  final LonoraAvatarState avatarState;

  /// The agent can take a voice call now (a direct conversation with an active agent).
  final bool callable;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final c = context.ln.colors;
    final a = agent;
    final g = group;
    final Widget avatar;
    if (a != null) {
      avatar = LonoraAvatar(
        agentId: a.id,
        face: a.avatar,
        color: a.color,
        tradesOnItsOwn: a.tradesOnItsOwn,
        state: avatarState,
        size: LnSize.avatarHeader,
      );
    } else if (g != null && members.isNotEmpty) {
      avatar = LonoraGroupAvatar(
        members: [
          for (final m in members)
            LonoraAvatarMember(
              agentId: m.id,
              face: m.avatar,
              color: m.color,
              tradesOnItsOwn: m.tradesOnItsOwn,
            ),
        ],
        size: LnSize.avatarHeader,
      );
    } else {
      avatar = Container(
        decoration: BoxDecoration(color: c.fill2, shape: BoxShape.circle),
      );
    }
    // The capsule opens the agent's profile, or the group's settings.
    final capsuleHint = l10n.t(
      g != null ? 'groupSettings' : 'conv_agentProfile',
    );
    return Stack(
      clipBehavior: Clip.none,
      children: [
        // Content scrolls beneath the transparent chrome: the band behind the circles and the
        // capsule is the canvas, fading out over the 22 dp above the first message.
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          height: conversationHeaderExtent(context),
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [c.bg, c.bg, c.bg.withValues(alpha: 0)],
                  stops: [0, 1 - 22 / conversationHeaderExtent(context), 1],
                ),
              ),
            ),
          ),
        ),
        ScreenHeader(
          leading: CircleIconButton(
            // Lucide chevrons mirror themselves in RTL (matchTextDirection).
            icon: const Icon(FIcons.chevronLeft),
            semanticLabel: l10n.t('back'),
            onTap: () => _back(context),
          ),
          center: TitleCapsule(
            avatar: avatar,
            title: title,
            semanticHint: a != null || g != null ? capsuleHint : null,
            onTap: a != null
                ? () => context.push(Routes.agent(a.id))
                : g != null
                ? () => context.push(Routes.groupSettings(g.id))
                : null,
          ),
          trailing: CircleIconButton(
            icon: const Icon(FIcons.ellipsis),
            semanticLabel: l10n.t('actions'),
            onTap: () => _actions(context),
          ),
        ),
      ],
    );
  }

  void _back(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Routes.chats);
    }
  }

  Future<void> _actions(BuildContext context) async {
    final l10n = context.l10n;
    final a = agent;
    final g = group;
    await showLnActionMenu<void>(
      context,
      actions: [
        if (a != null && callable)
          LnMenuAction(
            icon: FIcons.phone,
            label: l10n.t('callAgent'),
            onSelected: () =>
                VoiceCalls.start(context, agentId: a.id, threadId: threadId),
          ),
        LnMenuAction(
          icon: FIcons.chartCandlestick,
          label: l10n.t('charts'),
          onSelected: () =>
              context.push(Routes.charts(threadId: threadId, agentId: a?.id)),
        ),
        if (a != null)
          LnMenuAction(
            icon: FIcons.clock,
            label: l10n.t('routines'),
            onSelected: () => context.push(Routes.routines(agentId: a.id)),
          ),
        LnMenuAction(
          icon: FIcons.folder,
          label: l10n.t('artifacts'),
          onSelected: () => context.push(Routes.artifacts(threadId: threadId)),
        ),
        LnMenuAction(
          icon: FIcons.slidersHorizontal,
          label: l10n.t('chatPrefs'),
          onSelected: () => showChatPrefsSheet(context),
        ),
        if (a != null || g != null)
          LnMenuAction(
            icon: FIcons.settings,
            label: l10n.t(g != null ? 'groupSettings' : 'agentSettings'),
            onSelected: () => context.push(
              g != null
                  ? Routes.groupSettings(g.id)
                  : Routes.agentSettings(a!.id),
            ),
          ),
      ],
    );
  }
}

/// «تجربة المحادثة»: the per-device conversation preferences (apps/mobile/lib/chat-prefs.ts).
Future<void> showChatPrefsSheet(BuildContext context) {
  final l10n = context.l10n;
  return showLnSheet<void>(
    context,
    title: l10n.t('chatPrefs'),
    padding: const EdgeInsetsDirectional.fromSTEB(0, 0, 0, 16),
    builder: (sheet) => StoreConnector<AppState, ChatPrefs>(
      converter: (store) => store.state.prefs.chatPrefs,
      builder: (context, prefs) {
        LnListTile row(String key, bool value, ChatPrefs Function(bool) next) =>
            LnListTile(
              title: l10n.t(key),
              subtitle: l10n.t('${key}Sub'),
              trailing: LnSwitch(
                value: value,
                semanticLabel: l10n.t(key),
                onChanged: (v) => context.dispatch(SetChatPrefsAction(next(v))),
              ),
            );
        return SingleChildScrollView(
          child: LnSection(
            footer: l10n.t('chatPrefsIntro'),
            children: [
              row('prefSteps', prefs.steps, (v) => prefs.copyWith(steps: v)),
              row(
                'prefStepsOpen',
                prefs.stepsOpen,
                (v) => prefs.copyWith(stepsOpen: v),
              ),
              row(
                'prefAgentStatus',
                prefs.detailedStatus,
                (v) => prefs.copyWith(detailedStatus: v),
              ),
              row('prefAssist', prefs.assist, (v) => prefs.copyWith(assist: v)),
            ],
          ),
        );
      },
    ),
  );
}
