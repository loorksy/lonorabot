// Message links open only on a tap and never reach the connect flow: `lonora://connect` (in
// any case) and relative links that resolve outside charts and files push nothing and launch
// nothing; chart links route in the app and https opens outside it.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/features/rich/markdown_view.dart';

void main() {
  late List<String> visited;
  late List<String> platform;
  late BuildContext linkContext;

  Future<void> pumpRouter(WidgetTester tester) async {
    visited = [];
    platform = [];
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    // Every platform message is recorded: a launch would show up here, whichever
    // url_launcher implementation the test binding picked.
    messenger.allMessagesHandler = (channel, handler, message) async {
      platform.add(channel);
      if (channel.contains('url_launcher')) {
        return const StandardMethodCodec().encodeSuccessEnvelope(true);
      }
      return null;
    };
    addTearDown(() => messenger.allMessagesHandler = null);
    Widget page(BuildContext context, GoRouterState state) =>
        const SizedBox.shrink();
    final router = GoRouter(
      redirect: (context, state) {
        visited.add(state.uri.toString());
        return null;
      },
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => Builder(
            builder: (context) {
              linkContext = context;
              return const SizedBox.shrink();
            },
          ),
        ),
        GoRoute(path: '/connect', builder: page),
        GoRoute(path: '/charts', builder: page),
        GoRoute(path: '/files/:id', builder: page),
        GoRoute(path: '/thread/:id', builder: page),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();
    visited.clear();
    platform.clear();
  }

  for (final href in const [
    'lonora://connect?server=https://evil.example&token=abcdefghijklmnopqrstuv',
    'LONORA://Connect?server=https://evil.example',
    'lonora:connect?server=https://evil.example',
    '/connect?server=https://evil.example',
    '/charts/../connect?server=https://evil.example',
    '//evil.example/charts',
    'javascript:alert(1)',
    'intent://connect#Intent;scheme=lonora;end',
  ]) {
    testWidgets('$href pushes and launches nothing', (tester) async {
      await pumpRouter(tester);
      unawaited(openLink(linkContext, href));
      await tester.pumpAndSettle();
      expect(visited, isEmpty);
      expect(platform.where((c) => c.contains('url_launcher')), isEmpty);
    });
  }

  testWidgets('a chart link routes in the app', (tester) async {
    await pumpRouter(tester);
    // A push completes when the page is popped: not awaited.
    unawaited(openLink(linkContext, '/charts?symbol=XAUUSD'));
    await tester.pumpAndSettle();
    expect(visited, ['/charts?symbol=XAUUSD']);
  });

  testWidgets('an https link opens outside the app', (tester) async {
    await pumpRouter(tester);
    unawaited(openLink(linkContext, 'https://lonora.ai/market'));
    await tester.pumpAndSettle();
    expect(visited, isEmpty);
    expect(platform.where((c) => c.contains('url_launcher')), isNotEmpty);
  });
}
