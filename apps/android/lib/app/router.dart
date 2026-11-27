import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';

import '../features/agents/agent_memory_screen.dart';
import '../features/agents/agent_profile_screen.dart';
import '../features/agents/agent_settings_screen.dart';
import '../features/agents/instructions_screen.dart';
import '../features/agents/agents_screen.dart';
import '../features/attention/attention_screen.dart';
import '../features/auth/connect_screen.dart';
import '../features/auth/server_screen.dart';
import '../features/auth/sign_in_screen.dart';
import '../features/charts/charts_screen.dart';
import '../features/chats/archived_screen.dart';
import '../features/chats/chats_screen.dart';
import '../features/chats/search_screen.dart';
import '../features/conversation/conversation_screen.dart';
import '../features/files/artifact_screen.dart';
import '../features/files/artifacts_screen.dart';
import '../features/files/image_viewer_screen.dart';
import '../features/groups/group_settings_screen.dart';
import '../features/groups/new_group_screen.dart';
import '../features/market/market_screen.dart';
import '../features/me/me_screen.dart';
import '../features/me/owner_knowledge_screen.dart';
import '../features/routines/routines_screen.dart';
import '../features/settings/about_screen.dart';
import '../features/settings/account_screen.dart';
import '../features/settings/appearance_screen.dart';
import '../features/settings/integrations_screen.dart';
import '../features/settings/models_screen.dart';
import '../features/settings/notifications_screen.dart';
import '../features/settings/running_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/settings/usage_screen.dart';
import '../features/settings/voice_settings_screen.dart';
import '../features/skills/skills_screen.dart';
import '../features/tasks/tasks_screen.dart';
import '../state/app_state.dart';
import 'home_shell.dart';
import 'routes.dart';
import 'splash_screen.dart';

final rootNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'root');

/// Notifies go_router when the session status changes (redirect re-evaluation).
class _SessionListenable extends ChangeNotifier {
  _SessionListenable(Store<AppState> store) {
    _status = store.state.session.status;
    _sub = store.onChange.listen((state) {
      if (state.session.status != _status) {
        _status = state.session.status;
        notifyListeners();
      }
    });
  }
  late SessionStatus _status;
  late final StreamSubscription<AppState> _sub;

  @override
  void dispose() {
    _sub.cancel();
    super.dispose();
  }
}

/// A conversation is a page over the chat list: it slides in and, swiped back (or ≡), slides away
/// to reveal the list.
Page<void> _conversationPage(GoRouterState state, Widget child) =>
    CupertinoPage<void>(key: state.pageKey, child: child);

GoRouter buildRouter(Store<AppState> store) {
  final open = {Routes.signIn, Routes.connect, Routes.server};
  return GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: Routes.splash,
    refreshListenable: _SessionListenable(store),
    redirect: (context, state) {
      final status = store.state.session.status;
      final path = state.matchedLocation;
      if (status == SessionStatus.unknown) {
        return path == Routes.splash ? null : Routes.splash;
      }
      if (status == SessionStatus.signedOut) {
        return open.contains(path) ? null : Routes.signIn;
      }
      if (path == Routes.splash || path == Routes.signIn) return Routes.chats;
      return null;
    },
    routes: [
      GoRoute(path: Routes.splash, builder: (_, _) => const SplashScreen()),
      GoRoute(path: Routes.signIn, builder: (_, _) => const SignInScreen()),
      GoRoute(
        path: Routes.connect,
        builder: (_, s) => ConnectScreen(
          server: s.uri.queryParameters['server'] ?? '',
          token: s.uri.queryParameters['token'],
        ),
      ),
      GoRoute(path: Routes.server, builder: (_, _) => const ServerScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) =>
            HomeShell(shell: shell, location: state.uri.path),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.chats,
                builder: (_, _) => const ChatsScreen(),
                routes: [
                  GoRoute(
                    path: 'thread/:id',
                    pageBuilder: (_, s) => _conversationPage(
                      s,
                      ConversationScreen(
                        threadId: s.pathParameters['id']!,
                        around: int.tryParse(
                          s.uri.queryParameters['around'] ?? '',
                        ),
                      ),
                    ),
                  ),
                  GoRoute(
                    path: 'archived',
                    builder: (_, _) => const ArchivedScreen(),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.market,
                builder: (_, _) => const MarketScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(path: Routes.me, builder: (_, _) => const MeScreen()),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.attention,
                builder: (_, _) => const AttentionScreen(),
              ),
            ],
          ),
        ],
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.search,
        builder: (_, _) => const SearchScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.agents,
        builder: (_, _) => const AgentsScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: '/agent/:id',
        builder: (_, s) => AgentProfileScreen(agentId: s.pathParameters['id']!),
        routes: [
          GoRoute(
            path: 'settings',
            builder: (_, s) =>
                AgentSettingsScreen(agentId: s.pathParameters['id']!),
          ),
          GoRoute(
            path: 'memory',
            builder: (_, s) =>
                AgentMemoryScreen(agentId: s.pathParameters['id']!),
          ),
          GoRoute(
            path: 'instructions',
            builder: (_, s) =>
                AgentInstructionsScreen(agentId: s.pathParameters['id']!),
          ),
          GoRoute(
            path: 'skills',
            builder: (_, s) => SkillsScreen(agentId: s.pathParameters['id']!),
          ),
        ],
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: '/routines',
        builder: (_, s) =>
            RoutinesScreen(agentId: s.uri.queryParameters['agent']),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: '/groups/new',
        builder: (_, s) => NewGroupScreen(
          memberIds: (s.uri.queryParameters['members'] ?? '')
              .split(',')
              .where((e) => e.isNotEmpty)
              .toList(),
        ),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: '/groups/:id/settings',
        builder: (_, s) =>
            GroupSettingsScreen(groupId: s.pathParameters['id']!),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: '/files',
        builder: (_, s) => ArtifactsScreen(
          threadId: s.uri.queryParameters['thread'],
          agentId: s.uri.queryParameters['agent'],
        ),
        routes: [
          GoRoute(
            path: ':id',
            builder: (_, s) =>
                ArtifactScreen(artifactId: s.pathParameters['id']!),
            routes: [
              GoRoute(
                path: 'image',
                builder: (_, s) =>
                    ImageViewerScreen(artifactId: s.pathParameters['id']!),
              ),
            ],
          ),
        ],
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: '/charts',
        builder: (_, s) => ChartsScreen(
          threadId: s.uri.queryParameters['thread'],
          agentId: s.uri.queryParameters['agent'],
          chartId:
              s.uri.queryParameters['chart'] ??
              s.uri.queryParameters['chartId'],
        ),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.tasks,
        builder: (_, _) => const TasksScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.ownerKnowledge,
        builder: (_, _) => const OwnerKnowledgeScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.settings,
        builder: (_, _) => const SettingsScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.account,
        builder: (_, _) => const AccountScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.integrations,
        builder: (_, _) => const IntegrationsScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.models,
        builder: (_, _) => const ModelsScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.notifications,
        builder: (_, _) => const NotificationsScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.voice,
        builder: (_, _) => const VoiceSettingsScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.running,
        builder: (_, _) => const RunningScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.appearance,
        builder: (_, _) => const AppearanceScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.usage,
        builder: (_, _) => const UsageScreen(),
      ),
      GoRoute(
        parentNavigatorKey: rootNavigatorKey,
        path: Routes.about,
        builder: (_, _) => const AboutScreen(),
      ),
    ],
    errorBuilder: (context, state) => const SplashScreen(notFound: true),
  );
}
