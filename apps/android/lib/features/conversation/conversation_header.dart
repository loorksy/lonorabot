// Conversation header: Ø44 circles at the 16 dp gutter around the centred avatar + name capsule.
// At the start: the ☰ button of the chat drawer when this conversation is the Chats tab's
// last-conversation home (with the unread count of the other chats), else back. At the end: a
// call circle when the agent can take a call now. A tap on the capsule opens the conversation's
// actions, Lonora's thread menu (apps/mobile/app/thread.tsx ActionMenu) led by the agent's
// profile or the group's settings: charts, routines, files, chat experience, agent/group
// settings.
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
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../chats/chat_drawer.dart' show ChatDrawerScope;
import '../chats/chats_home.dart' show unreadElsewhere;
import '../chats/chats_strings.dart';
import '../voice/voice_api.dart';
import 'conversation_strings.dart';

/// Height from the screen top to the first message (22 dp under the capsule).
double conversationHeaderExtent(BuildContext context) =>
    MediaQuery.paddingOf(context).top +
    ScreenHeader.topGapDefault -
    2 +
    2 +
    TitleCapsule.height +
    22;

/// The header circles' bottom: the canvas hides the transcript down to here.
double _circlesBottom(BuildContext context) =>
    MediaQuery.paddingOf(context).top +
    ScreenHeader.topGapDefault +
    LnSize.headerCircle;

/// Where the header's fade ends: the transcript is fully visible ≈64 dp under the capsule.
double conversationFadeExtent(BuildContext context) =>
    conversationHeaderExtent(context) - 22 + 64;

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
    this.home = false,
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

  /// This conversation is the Chats tab's last-conversation home: the start circle opens the
  /// chat drawer instead of going back.
  final bool home;

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
    final drawer = home ? ChatDrawerScope.maybeOf(context) : null;
    final Widget leading;
    if (drawer != null) {
      registerChatsStrings();
      final unread = context.select(
        (AppState s) => unreadElsewhere(s.shell, threadId),
      );
      leading = MenuPillButton(
        semanticLabel: l10n.t('chats_drawer'),
        unreadCount: unread,
        unreadLabel: l10n.t('sh_unreadN', const [], {'count': unread}),
        onTap: drawer.toggle,
      );
    } else {
      leading = CircleIconButton(
        // Lucide chevrons mirror themselves in RTL (matchTextDirection).
        icon: const Icon(FIcons.chevronLeft),
        semanticLabel: l10n.t('back'),
        onTap: () => _back(context),
      );
    }
    return Stack(
      clipBehavior: Clip.none,
      children: [
        // Content scrolls beneath the transparent chrome: the canvas hides it down to the
        // circles' bottom, then fades it in over the ≈64 dp under the capsule.
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          height: conversationFadeExtent(context),
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [c.bg, c.bg, c.bg.withValues(alpha: 0)],
                  stops: [
                    0,
                    _circlesBottom(context) / conversationFadeExtent(context),
                    1,
                  ],
                ),
              ),
            ),
          ),
        ),
        ScreenHeader(
          leading: leading,
          center: Builder(
            builder: (capsule) => TitleCapsule(
              avatar: avatar,
              title: title,
              semanticHint: _actionsLabel(l10n),
              onTap: () => _actions(capsule),
            ),
          ),
          trailing: a != null && callable
              ? CircleIconButton(
                  icon: const Icon(FIcons.phone),
                  semanticLabel: l10n.t('callAgent'),
                  onTap: () => VoiceCalls.start(
                    context,
                    agentId: a.id,
                    threadId: threadId,
                  ),
                )
              : null,
        ),
      ],
    );
  }

  /// The capsule's hint and its menu's name: the agent's actions, or the group's.
  String _actionsLabel(L10n l10n) {
    if (agent == null && group != null) {
      registerConversationStrings(l10n);
      return l10n.t('conv_groupActions');
    }
    return l10n.t('actions');
  }

  void _back(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Routes.chats);
    }
  }

  /// The conversation's actions, under the capsule ([capsule] is its context).
  Future<void> _actions(BuildContext capsule) async {
    final l10n = capsule.l10n;
    final a = agent;
    final g = group;
    final box = capsule.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    // The name pill, not the avatar above it: the menu hangs from the pill's bottom.
    final pill =
        box.localToGlobal(const Offset(0, TitleCapsule.pillOffset)) &
        Size(box.size.width, LnSize.namePill);
    await showLnPopoverMenu<void>(
      capsule,
      anchorRect: pill,
      semanticLabel: _actionsLabel(l10n),
      actions: [
        if (a != null)
          LnMenuAction(
            icon: FIcons.userRound,
            label: l10n.t('conv_agentProfile'),
            onSelected: () => capsule.push(Routes.agent(a.id)),
          )
        else if (g != null)
          LnMenuAction(
            icon: FIcons.usersRound,
            label: l10n.t('groupSettings'),
            onSelected: () => capsule.push(Routes.groupSettings(g.id)),
          ),
        LnMenuAction(
          icon: FIcons.chartCandlestick,
          label: l10n.t('charts'),
          onSelected: () =>
              capsule.push(Routes.charts(threadId: threadId, agentId: a?.id)),
        ),
        if (a != null)
          LnMenuAction(
            icon: FIcons.clock,
            label: l10n.t('routines'),
            onSelected: () => capsule.push(Routes.routines(agentId: a.id)),
          ),
        LnMenuAction(
          icon: FIcons.folder,
          label: l10n.t('artifacts'),
          onSelected: () => capsule.push(Routes.artifacts(threadId: threadId)),
        ),
        LnMenuAction(
          icon: FIcons.slidersHorizontal,
          label: l10n.t('chatPrefs'),
          onSelected: () => showChatPrefsSheet(capsule),
        ),
        if (a != null)
          LnMenuAction(
            icon: FIcons.settings,
            label: l10n.t('agentSettings'),
            onSelected: () => capsule.push(Routes.agentSettings(a.id)),
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
