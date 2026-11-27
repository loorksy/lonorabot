// Every WP-A2 page and sheet lays out at 1.3× text without overflow (in both languages), and a
// pushed sub-page goes back with its header circle.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:lonora/core/json.dart';
import 'package:lonora/features/settings/integrations/broker_pages.dart';
import 'package:lonora/features/settings/integrations/mcp_pages.dart';
import 'package:lonora/features/settings/integrations/providers_page.dart';
import 'package:lonora/features/settings/integrations_screen.dart';
import 'package:lonora/features/settings/models_screen.dart';
import 'package:lonora/features/settings/running_screen.dart';
import 'package:lonora/features/settings/usage_screen.dart';

import 'ext_harness.dart';
import 'fixtures.dart';

void main() {
  setUpAll(setUpExtTests);

  void allRoutes(QueryApi api) {
    integrationsRoutes(api);
    modelsRoutes(api);
    usageRoutes(api);
    api
      ..on('GET /workspace/running', (_) => runningJson)
      ..on('GET /runs', (_) => [for (final r in activeRuns()) r.raw])
      ..on(
        'GET /trading/accounts/c-exness',
        (_) => {
          'account': {
            'balance': '10250.40',
            'currency': 'USD',
            'broker': 'Exness',
            'login': '7310455',
            'server': 'Exness-MT5Real8',
          },
        },
      )
      ..on('GET /market/symbols', (_) => ['XAUUSD', 'EURUSD'])
      ..on(
        'POST /trusted-sources/mcp/m-calendar/preview',
        (_) => {
          'id': 'm-calendar',
          'digest': 'a' * 64,
          'tools': ['list_events', 'create_event', 'pay_invoice'],
          'writes': ['create_event'],
          'blocked': ['pay_invoice'],
          'titles': {'list_events': 'List the events of a calendar'},
        },
      );
  }

  /// Integrations without Telegram, so its sheet asks for a bot token.
  void noTelegram(QueryApi api) {
    allRoutes(api);
    api.on(
      'GET /capabilities',
      (_) => {
        ...capabilitiesJson,
        'integrations': [
          for (final i in asJsonList(capabilitiesJson['integrations']))
            if (i['type'] != 'telegram') i,
        ],
      },
    );
  }

  final pages = <String, Widget>{
    'integrations': const IntegrationsScreen(),
    'providers': const ProvidersPage(),
    'provider key': const ProviderKeyPage(provider: 'openai', configured: true),
    'broker form': const BrokerFormPage(),
    'add MCP': const McpFormPage(),
    'broker account': const BrokerAccountPage(connectionId: 'c-exness'),
    'models': const ModelsScreen(),
    'usage': const UsageScreen(),
    'usage detail': const UsageDetailPage(agentId: 'a-gold'),
    'running': const RunningScreen(),
  };

  for (final locale in ['ar', 'en']) {
    for (final MapEntry(key: name, value: page) in pages.entries) {
      testWidgets('$name lays out at 1.3x text ($locale)', (tester) async {
        tester.platformDispatcher.textScaleFactorTestValue = 1.3;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        await setUpExtServices(allRoutes);
        final store = extStore(locale: locale, agents: agents);
        await pumpExt(tester, store, page);
        // Scroll through the whole page so every row is built and laid out.
        final scrollable = find.byType(Scrollable).first;
        for (var i = 0; i < 12; i++) {
          await tester.drag(scrollable, const Offset(0, -500));
          await tester.pump();
        }
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      });
    }
  }

  // Each sheet, opened from its page: (page, routes, the row that opens it, a step inside).
  final sheets =
      <
        String,
        ({
          Widget page,
          void Function(QueryApi) routes,
          Finder Function(String locale) row,
          String Function(String locale)? then,
        })
      >{
        'trusted sources': (
          page: const IntegrationsScreen(),
          routes: allRoutes,
          row: (l) =>
              find.text(l == 'ar' ? 'المصادر الموثوقة' : 'Trusted sources'),
          then: null,
        ),
        'MCP review': (
          page: const IntegrationsScreen(),
          routes: allRoutes,
          row: (_) => find.textContaining('Calendar'),
          then: (l) => l == 'ar' ? 'مراجعة الأدوات' : 'Review the tools',
        ),
        'news domains': (
          page: const IntegrationsScreen(),
          routes: allRoutes,
          row: (l) => find.text(l == 'ar' ? 'نطاقات الأخبار' : 'News domains'),
          then: null,
        ),
        'RSS feeds': (
          page: const IntegrationsScreen(),
          routes: allRoutes,
          row: (l) => find.text(l == 'ar' ? 'خلاصات RSS' : 'RSS feeds'),
          then: null,
        ),
        'Telegram linked': (
          page: const IntegrationsScreen(),
          routes: allRoutes,
          row: (_) => find.text('Telegram'),
          then: null,
        ),
        'Telegram link': (
          page: const IntegrationsScreen(),
          routes: noTelegram,
          row: (_) => find.text('Telegram'),
          then: null,
        ),
        'model picker': (
          page: const ModelsScreen(),
          routes: allRoutes,
          row: (l) => find.text(l == 'ar' ? 'النموذج الموحد' : 'Unified model'),
          then: null,
        ),
      };

  for (final locale in ['ar', 'en']) {
    for (final MapEntry(key: name, value: sheet) in sheets.entries) {
      testWidgets('$name sheet lays out at 1.3x text ($locale)', (
        tester,
      ) async {
        tester.platformDispatcher.textScaleFactorTestValue = 1.3;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        await setUpExtServices(sheet.routes);
        final store = extStore(locale: locale, agents: agents);
        await pumpExt(tester, store, sheet.page);
        final row = sheet.row(locale);
        await scrollTo(tester, row);
        await tapAndSettle(tester, row);
        if (sheet.then != null) {
          await tapAndSettle(tester, find.text(sheet.then!(locale)));
        }
        // The sheet covers the page.
        expect(
          ModalRoute.of(tester.element(pageScrollable))!.isCurrent,
          isFalse,
        );
        // Scroll the sheet's own list to its end.
        final inner = find.byType(Scrollable).last;
        for (var i = 0; i < 6; i++) {
          await tester.drag(inner, const Offset(0, -400));
          await tester.pump();
        }
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('a pushed sub-page goes back with its header circle', (
    tester,
  ) async {
    await setUpExtServices(allRoutes);
    final store = extStore(agents: agents);
    await pumpExt(tester, store, const ProvidersPage());
    await tapAndSettle(tester, find.text('DeepSeek'));
    expect(find.byType(ProviderKeyPage), findsOneWidget);
    await tapAndSettle(tester, find.byIcon(FIcons.chevronLeft));
    expect(find.byType(ProviderKeyPage), findsNothing);
    expect(find.byType(ProvidersPage), findsOneWidget);
  });
}
