// Integrations, model providers, trading accounts, MCP servers, news and channels: what they
// read, what they write (and never echo), the confirmations, and the goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/settings_ext
import 'dart:async';
import 'dart:convert';

import 'package:file_picker/file_picker.dart' show FilePickerPlatform;
import 'package:flutter/material.dart' show TextField;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons, FTile;
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/design/design.dart' show BlockButton, LnListTile;
import 'package:lonora/features/settings/integrations/broker_pages.dart'
    show BrokerAccountPage, BrokerFormPage;
import 'package:lonora/features/settings/integrations/mcp_pages.dart'
    show McpFormPage;
import 'package:lonora/features/settings/integrations/providers_page.dart';
import 'package:lonora/features/settings/integrations_screen.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart' show realtime;

import '../../design/harness.dart';
import 'ext_harness.dart';
import 'fixtures.dart';

void main() {
  setUpAll(setUpExtTests);

  Future<QueryApi> pumpPage(
    WidgetTester tester,
    Widget page, {
    String locale = 'en',
    AppThemeMode theme = AppThemeMode.light,
    void Function(QueryApi api)? routes,
  }) async {
    final api = await setUpExtServices((api) {
      integrationsRoutes(api);
      routes?.call(api);
    });
    final store = extStore(locale: locale, theme: theme, agents: agents);
    await pumpExt(tester, store, page);
    return api;
  }

  Future<void> flushToasts(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  }

  /// The toast's kind, by its badge icon (13 dp).
  Finder toastIcon(IconData icon) => find.byWidgetPredicate(
    (w) => w is Icon && w.icon == icon && w.size == 13,
  );

  /// The position of the first call to [method] [path] in the order sent.
  int order(ScriptedApi api, String method, String path) =>
      api.calls.indexWhere((c) => c.method == method && c.path == path);

  /// Every text the screen shows, for checking a secret is nowhere.
  String screenText(WidgetTester tester) => [
    for (final t in tester.widgetList<Text>(find.byType(Text)))
      t.data ?? t.textSpan?.toPlainText() ?? '',
    for (final e in tester.widgetList<EditableText>(find.byType(EditableText)))
      e.controller.text,
  ].join('\n');

  group('integrations page', () {
    testWidgets('lists accounts, providers, servers, channels and skills', (
      tester,
    ) async {
      await pumpPage(tester, const IntegrationsScreen());
      expect(find.textContaining('Exness'), findsOneWidget);
      expect(find.textContaining('7310455'), findsOneWidget);
      // A simulation is labelled as one, never as a broker account.
      expect(find.text('Simulation'), findsOneWidget);
      expect(find.text('Broker account'), findsOneWidget);
      expect(find.text('Add a trading account'), findsOneWidget);
      expect(find.text('3'), findsOneWidget); // configured providers
      await scrollTo(tester, find.textContaining('Research tools'));
      expect(find.text('Trusted'), findsWidgets);
      expect(find.text('Not approved'), findsOneWidget);
      await scrollTo(tester, find.text('Telegram'));
      expect(find.textContaining('your messages reach'), findsOneWidget);
      await scrollTo(tester, find.textContaining('Risk check'));
      expect(find.textContaining('acme/trading-skills'), findsOneWidget);
      await scrollTo(tester, find.textContaining('GITHUB_TOKEN'));
      // Secrets are listed by name only.
      expect(find.textContaining('Names only'), findsOneWidget);
    });

    testWidgets('a server is reviewed, then trusted with the preview digest', (
      tester,
    ) async {
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: (api) => api
          ..on(
            'POST /trusted-sources/mcp/m-calendar/preview',
            (_) => {
              'id': 'm-calendar',
              'digest': 'a' * 64,
              'tools': ['list_events', 'create_event', 'pay_invoice'],
              'writes': ['create_event'],
              'blocked': ['pay_invoice'],
              'titles': {'list_events': 'List events'},
            },
          ),
      );
      await scrollTo(tester, find.textContaining('Calendar'));
      await tapAndSettle(tester, find.textContaining('Calendar').first);
      expect(find.text('Review the tools'), findsOneWidget);
      await tapAndSettle(tester, find.text('Review the tools'));
      expect(find.textContaining('List events'), findsOneWidget);
      expect(find.textContaining('could move money'), findsOneWidget);
      // A blocked money tool: the server is trusted to read only.
      expect(find.text('Approve with non-financial writes'), findsNothing);
      await tapAndSettle(tester, find.text('Approve the server'));
      final trust = api
          .callsTo('POST', '/trusted-sources/mcp/m-calendar')
          .single;
      expect(trust.body, {'tier': 'read', 'digest': 'a' * 64});
      await flushToasts(tester);
    });

    testWidgets('unlinking Telegram asks first', (tester) async {
      final api = await pumpPage(tester, const IntegrationsScreen());
      await scrollTo(tester, find.text('Telegram'));
      await tapAndSettle(tester, find.text('Telegram'));
      expect(find.text('••••••••••••'), findsOneWidget);
      await tapAndSettle(tester, find.text('Unlink'));
      expect(find.text('Unlink Telegram?'), findsOneWidget);
      await tapAndSettle(tester, find.text('Cancel'));
      expect(api.callsTo('DELETE', '/integrations/i-telegram'), isEmpty);
      await tapAndSettle(tester, find.text('Unlink'));
      await tapAndSettle(tester, find.text('Unlink').last);
      expect(api.callsTo('DELETE', '/integrations/i-telegram'), hasLength(1));
      await flushToasts(tester);
    });

    testWidgets('a news domain is removed after a confirmation', (
      tester,
    ) async {
      final api = await pumpPage(tester, const IntegrationsScreen());
      await scrollTo(tester, find.text('News domains'));
      await tapAndSettle(tester, find.text('News domains'));
      // The first domain's remove button.
      await tapAndSettle(tester, find.byIcon(FIcons.x).first);
      expect(find.textContaining('reuters.com\u2069?'), findsOneWidget);
      await tapAndSettle(tester, find.text('Remove').last);
      expect(
        api.callsTo('POST', '/trusted-sources/s-reuters/revoke'),
        hasLength(1),
      );
      await flushToasts(tester);
    });

    testWidgets('undoing a skill version sends the current revision', (
      tester,
    ) async {
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: (api) => api.on(
          'GET /agents/a-gold/skills/revocations',
          (_) => {'revision': 7, 'revoked': []},
        ),
      );
      await scrollTo(tester, find.textContaining('Risk check'));
      await tapAndSettle(tester, find.text('Undo').first);
      expect(find.text('Undo this version?'), findsOneWidget);
      await tapAndSettle(tester, find.text('Undo').last);
      final post = api
          .callsTo('POST', '/agents/a-gold/skills/revocations')
          .single;
      expect(post.body, {
        'skill_id': 'risk-check',
        'version': '3',
        'expected_revision': 7,
      });
      await flushToasts(tester);
    });

    testWidgets('a failed capability read keeps the rest and offers a retry', (
      tester,
    ) async {
      var fail = true;
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: (api) => api.on('GET /capabilities', (_) {
          if (fail) throw ApiError(status: 503, code: 'database_unavailable');
          return capabilitiesJson;
        }),
      );
      expect(find.textContaining('Exness'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
      fail = false;
      await tapAndSettle(tester, find.text('Retry'));
      expect(api.callsTo('GET', '/capabilities'), hasLength(2));
      await scrollTo(tester, find.textContaining('Research tools'));
      expect(find.text('Retry'), findsNothing);
    });

    testWidgets('offline first read offers a retry', (tester) async {
      await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: (api) {
          for (final r in [
            'GET /capabilities',
            'GET /trading/connections',
            'GET /providers',
            'GET /secrets',
          ]) {
            api.on(r, (_) => throw ApiError.network());
          }
        },
      );
      expect(find.textContaining('Could not connect'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
    });

    for (final v in goldenVariants) {
      testWidgets('golden ${v.name}', (tester) async {
        await withRealShadows(() async {
          await pumpPage(
            tester,
            const IntegrationsScreen(),
            locale: v.locale,
            theme: v.theme,
          );
          await expectLater(
            find.byType(WidgetsApp),
            matchesGoldenFile('goldens/integrations_${v.name}.png'),
          );
        });
      });
    }
  });

  testWidgets('golden lower sections light_ar', (tester) async {
    await withRealShadows(() async {
      await pumpPage(tester, const IntegrationsScreen(), locale: 'ar');
      await tester.drag(pageScrollable, const Offset(0, -1500));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(WidgetsApp),
        matchesGoldenFile('goldens/integrations_lower_light_ar.png'),
      );
    });
  });

  testWidgets('ms:C11 an integration\'s state is its subtitle, not its title', (
    tester,
  ) async {
    await pumpPage(tester, const IntegrationsScreen());
    final title = find.textContaining('Forex calendar');
    await scrollTo(tester, title);
    final text = tester.widget<Text>(title).data!;
    expect(text, startsWith('Economic calendar'));
    expect(text, isNot(endsWith('on')));
    final row = find.ancestor(of: title, matching: find.byType(FTile));
    expect(find.descendant(of: row, matching: find.text('On')), findsOneWidget);
  });

  testWidgets('ms:C11 a nameless integration of an unknown type', (
    tester,
  ) async {
    await pumpPage(
      tester,
      const IntegrationsScreen(),
      routes: (api) => api.on(
        'GET /capabilities',
        (_) => {
          ...capabilitiesJson,
          'integrations': [
            // `enabled` read as the core line reads it (truthiness), not as a strict bool.
            {'id': 'i-x', 'type': 'future_feed', 'enabled': 1},
          ],
        },
      ),
    );
    final title = find.text('Unnamed');
    await scrollTo(tester, title);
    expect(find.textContaining('future_feed'), findsNothing);
    final row = find.ancestor(of: title, matching: find.byType(FTile));
    expect(find.descendant(of: row, matching: find.text('On')), findsOneWidget);
  });

  testWidgets('golden lower sections dark_en', (tester) async {
    await withRealShadows(() async {
      await pumpPage(
        tester,
        const IntegrationsScreen(),
        theme: AppThemeMode.dark,
      );
      await tester.drag(pageScrollable, const Offset(0, -3000));
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(WidgetsApp),
        matchesGoldenFile('goldens/integrations_bottom_dark_en.png'),
      );
    });
  });

  group('model providers', () {
    testWidgets('lists key providers and the ChatGPT plan', (tester) async {
      await pumpPage(tester, const ProvidersPage());
      expect(find.text('OpenAI'), findsOneWidget);
      expect(find.text('Anthropic'), findsOneWidget);
      expect(find.text('Not configured'), findsNWidgets(3));
      expect(find.text('Manage usage'), findsOneWidget);
      expect(find.textContaining('owner@example.com'), findsOneWidget);
      // It opens the browser: the up-right arrow, never the chevron.
      final row = find.ancestor(
        of: find.text('Manage usage'),
        matching: find.byType(FTile),
      );
      expect(
        find.descendant(of: row, matching: find.byIcon(FIcons.arrowUpRight)),
        findsOneWidget,
      );
      expect(
        find.descendant(of: row, matching: find.byIcon(FIcons.chevronRight)),
        findsNothing,
      );
    });

    testWidgets('a key is tested, saved, cleared and never shown', (
      tester,
    ) async {
      const key = 'sk-test-0123456789abcdef';
      final api = await pumpPage(
        tester,
        const ProvidersPage(),
        routes: (api) => api
          ..on('POST /providers/deepseek/test', (_) => {'ok': true})
          ..on(
            'PUT /providers/deepseek/credential',
            (_) => {'configured': true},
          ),
      );
      await tapAndSettle(tester, find.text('DeepSeek'));
      expect(find.text('Add a provider credential'), findsOneWidget);
      final field = find.byType(EditableText);
      expect(tester.widget<EditableText>(field).obscureText, isTrue);
      await tester.enterText(field, key);
      await tapAndSettle(tester, find.text('Test the connection'));
      expect(find.text('The connection works'), findsOneWidget);
      expect(api.callsTo('POST', '/providers/deepseek/test').single.body, {
        'api_key': key,
      });
      await tapAndSettle(tester, find.text('Save the key'));
      expect(api.callsTo('PUT', '/providers/deepseek/credential').single.body, {
        'api_key': key,
      });
      expect(find.byType(ProviderKeyPage), findsNothing);
      expect(find.text('Saved'), findsOneWidget);
      // The providers are read again; the key itself appears nowhere.
      expect(api.callsTo('GET', '/providers'), hasLength(2));
      expect(find.textContaining(key), findsNothing);
      await flushToasts(tester);
    });

    testWidgets('a rejected key shows the server reason', (tester) async {
      await pumpPage(
        tester,
        const ProviderKeyPage(provider: 'openai', configured: true),
        routes: (api) => api.on(
          'POST /providers/openai/test',
          (_) =>
              throw ApiError(status: 422, code: 'model_credentials_rejected'),
        ),
      );
      expect(find.text('Credential configured'), findsOneWidget);
      await tester.enterText(find.byType(EditableText), 'sk-wrong-key-123');
      await tapAndSettle(tester, find.text('Test the connection'));
      expect(find.text('The provider rejected this API key.'), findsOneWidget);
    });

    testWidgets('golden providers light_ar', (tester) async {
      await withRealShadows(() async {
        await pumpPage(tester, const ProvidersPage(), locale: 'ar');
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/providers_light_ar.png'),
        );
      });
    });

    testWidgets('golden provider key dark_en', (tester) async {
      await withRealShadows(() async {
        await pumpPage(
          tester,
          const ProviderKeyPage(provider: 'openai', configured: true),
          theme: AppThemeMode.dark,
        );
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/provider_key_dark_en.png'),
        );
      });
    });
  });

  group('trading accounts', () {
    void accountRoutes(QueryApi api) => api
      ..on(
        'GET /trading/accounts/c-exness',
        (_) => {
          'account': {
            'id': 'c-exness',
            'currency': 'USD',
            'balance': '10250.40',
            'equity': '10310.12',
            'margin': '0',
            'free_margin': '10310.12',
            'observed_at': '2026-11-27T11:00:00Z',
            'broker': 'Exness',
            'login': '7310455',
            'server': 'Exness-MT5Real8',
          },
          'positions': [],
          'orders': [],
        },
      )
      ..on(
        'GET /market/symbols',
        (_) => ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'BTCUSD'],
      );

    testWidgets('an account shows its balance, symbols and agents', (
      tester,
    ) async {
      final api = await pumpPage(
        tester,
        const BrokerAccountPage(connectionId: 'c-exness'),
        routes: accountRoutes,
      );
      expect(find.textContaining('10,250.40 USD'), findsOneWidget);
      expect(find.text('XAUUSD'), findsOneWidget);
      expect(api.gets.where((g) => g.path == '/market/symbols').single.query, {
        'account_id': 'c-exness',
      });
      await scrollTo(tester, find.text('متداول الذهب').last);
      expect(find.textContaining('Mandate'), findsOneWidget);
      await tapAndSettle(tester, find.text('متداول الذهب').last);
      expect(find.text('stub:/agent/a-gold/settings'), findsOneWidget);
    });

    testWidgets('«Outage and recovery» of the account: its state while down', (
      tester,
    ) async {
      final api = await pumpPage(
        tester,
        const BrokerAccountPage(connectionId: 'c-exness'),
        routes: (api) {
          accountRoutes(api);
          api.on(
            'GET /trading/connections',
            (_) => [
              {
                ...connectionsJson.first,
                'state': {
                  ...(connectionsJson.first['state']! as Map<String, Object?>),
                  'broker_recovery': {'status': 'recovering'},
                },
              },
              ...connectionsJson.skip(1),
            ],
          );
        },
      );
      final row = find.text('Outage and recovery');
      await scrollTo(tester, row);
      expect(find.text('Reconnecting'), findsOneWidget);
      await tapAndSettle(tester, row);
      expect(
        find.text('stub:/settings/recovery?account=c-exness'),
        findsOneWidget,
      );
      expect(api.calls.where((c) => c.method != 'GET'), isEmpty);
    });

    testWidgets('unlinking says what happens and asks first', (tester) async {
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: accountRoutes,
      );
      await tapAndSettle(tester, find.textContaining('Exness'));
      await scrollTo(tester, find.text('Unlink the account'));
      await tapAndSettle(tester, find.text('Unlink the account'));
      expect(find.textContaining('Execute with approval'), findsOneWidget);
      expect(api.callsTo('DELETE', '/trading/connections/c-exness'), isEmpty);
      await tapAndSettle(tester, find.text('Unlink'));
      expect(
        api.callsTo('DELETE', '/trading/connections/c-exness'),
        hasLength(1),
      );
      // Back on the integrations page, which says so and reads the accounts again.
      expect(find.byType(BrokerAccountPage), findsNothing);
      expect(find.textContaining('is unlinked'), findsOneWidget);
      expect(api.callsTo('GET', '/trading/connections'), hasLength(3));
      // The shell reads its agents again (their account was cleared by the server).
      expect(api.callsTo('GET', '/agents'), hasLength(1));
      await flushToasts(tester);
    });

    testWidgets('linking a simulation checks the fields with the server', (
      tester,
    ) async {
      final linked = <Json>[];
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: (api) => api
          ..on(
            'GET /trading/connections',
            (_) => [...connectionsJson, ...linked],
          )
          ..on(
            'GET /trading/accounts/c-new',
            (_) => throw ApiError(
              status: 409,
              code: 'simulation_snapshot_required',
            ),
          )
          ..on(
            'POST /trading/connections/test',
            (_) => {'ok': true, 'provider': 'simulation'},
          )
          ..on(
            'POST /trading/connections',
            (body) =>
                (linked..add({
                      ...connectionsJson[1],
                      'id': 'c-new',
                      'payload': {
                        ...asJson(connectionsJson[1]['payload']),
                        'account_id': 'paper-02',
                      },
                    }))
                    .last,
          ),
      );
      await tapAndSettle(tester, find.text('Add a trading account'));
      await tapAndSettle(
        tester,
        find.text('Simulation with an imported snapshot'),
      );
      await tester.enterText(find.byType(EditableText).first, 'paper-02');
      await tapAndSettle(tester, find.text('Check the fields'));
      expect(find.textContaining('not linked yet'), findsOneWidget);
      expect(api.callsTo('POST', '/trading/connections/test').single.body, {
        'provider': 'simulation',
        'enabled': true,
        'account_id': 'paper-02',
      });
      await scrollTo(tester, find.text('Link the account'));
      await tapAndSettle(tester, find.text('Link the account'));
      expect(api.callsTo('POST', '/trading/connections'), hasLength(1));
      // The new account opens, asking for its market snapshot.
      expect(find.text('The account is linked'), findsOneWidget);
      expect(find.text('Import the simulation data'), findsOneWidget);
      // Never an order path.
      expect(api.calls.where((c) => c.path.contains('execute')), isEmpty);
      await flushToasts(tester);
    });

    testWidgets('golden account light_en', (tester) async {
      await withRealShadows(() async {
        await pumpPage(
          tester,
          const BrokerAccountPage(connectionId: 'c-exness'),
          routes: accountRoutes,
        );
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/broker_account_light_en.png'),
        );
      });
    });
  });

  group('trusted sources', () {
    testWidgets('every source is listed; a removed one is restored at once', (
      tester,
    ) async {
      final api = await pumpPage(tester, const IntegrationsScreen());
      await scrollTo(tester, find.text('Trusted sources'));
      expect(find.text('Removed: 1'), findsOneWidget);
      await tapAndSettle(tester, find.text('Trusted sources'));
      expect(find.textContaining('old.example.com'), findsWidgets);
      expect(find.textContaining('removed'), findsOneWidget);
      expect(find.text('Restore'), findsOneWidget);
      expect(find.text('Remove'), findsNWidgets(4));
      final reads = api.callsTo('GET', '/capabilities').length;
      await tapAndSettle(tester, find.text('Restore'));
      // Restoring widens nothing new: no confirmation.
      expect(
        api.callsTo('POST', '/trusted-sources/s-old/restore'),
        hasLength(1),
      );
      expect(api.callsTo('GET', '/capabilities').length, reads + 1);
    });

    testWidgets('removing a source asks first', (tester) async {
      final api = await pumpPage(tester, const IntegrationsScreen());
      await scrollTo(tester, find.text('Trusted sources'));
      await tapAndSettle(tester, find.text('Trusted sources'));
      // The rows: github, reuters, ft, old (removed), Research tools.
      await tapAndSettle(tester, find.text('Remove').at(1));
      expect(find.textContaining('reuters.com\u2069?'), findsOneWidget);
      await tapAndSettle(tester, find.text('Cancel'));
      expect(api.callsTo('POST', '/trusted-sources/s-reuters/revoke'), isEmpty);
      await tapAndSettle(tester, find.text('Remove').at(1));
      await tapAndSettle(tester, find.text('Remove').last);
      expect(
        api.callsTo('POST', '/trusted-sources/s-reuters/revoke'),
        hasLength(1),
      );
    });

    testWidgets('golden trusted sources light_ar', (tester) async {
      await withRealShadows(() async {
        await pumpPage(tester, const IntegrationsScreen(), locale: 'ar');
        await scrollTo(tester, find.text('المصادر الموثوقة'));
        await tapAndSettle(tester, find.text('المصادر الموثوقة'));
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/trusted_sources_light_ar.png'),
        );
      });
    });
  });

  group('MCP servers', () {
    void mcpRoutes(QueryApi api) => api
      ..on('POST /integrations/secrets', (_) => {'id': 'sec-new'})
      ..on('POST /mcp', (body) => {'id': 'm-new'});

    Future<void> openForm(WidgetTester tester) async {
      await scrollTo(tester, find.text('Add an MCP server'));
      await tapAndSettle(tester, find.text('Add an MCP server'));
      expect(find.byType(McpFormPage), findsOneWidget);
    }

    Finder field(String label) => find.descendant(
      of: find
          .ancestor(of: find.text(label), matching: find.byType(Column))
          .first,
      matching: find.byType(EditableText),
    );

    testWidgets('a token is stored as a secret first, then the server', (
      tester,
    ) async {
      const token = 'mcp-token-0123456789abcdef';
      final name = 'R' * 80;
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: mcpRoutes,
      );
      await openForm(tester);
      await tester.enterText(field('Server name'), '${name}overflow');
      await tester.enterText(
        field('Server address'),
        'https://mcp.example.com/mcp',
      );
      await tapAndSettle(tester, find.text('Access token'));
      final secret = field(
        'Access token — stored encrypted, never shown again',
      );
      expect(tester.widget<EditableText>(secret).obscureText, isTrue);
      await tester.enterText(secret, token);
      await scrollTo(tester, find.text('Add the server'));
      await tapAndSettle(tester, find.text('Add the server'));
      final store = api.callsTo('POST', '/integrations/secrets').single;
      expect(store.body, {'name': 'mcp-${'R' * 76}', 'value': token});
      final add = api.callsTo('POST', '/mcp').single;
      expect(add.body, {
        'payload': {
          'name': name,
          'url': 'https://mcp.example.com/mcp',
          'secret_id': 'sec-new',
          'enabled': true,
        },
      });
      expect(
        order(api, 'POST', '/integrations/secrets'),
        lessThan(order(api, 'POST', '/mcp')),
      );
      // The value went out once, to the secret store, and is shown nowhere.
      expect(jsonEncode(add.body), isNot(contains(token)));
      expect(find.byType(McpFormPage), findsNothing);
      expect(find.text('The server is added'), findsOneWidget);
      expect(screenText(tester), isNot(contains(token)));
      await flushToasts(tester);
    });

    testWidgets('no authentication sends no secret', (tester) async {
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: mcpRoutes,
      );
      await openForm(tester);
      await tester.enterText(field('Server name'), 'Docs');
      await tester.enterText(
        field('Server address'),
        'https://docs.example/mcp',
      );
      await scrollTo(tester, find.text('Add the server'));
      await tapAndSettle(tester, find.text('Add the server'));
      expect(api.callsTo('POST', '/integrations/secrets'), isEmpty);
      expect(api.callsTo('POST', '/mcp').single.body, {
        'payload': {
          'name': 'Docs',
          'url': 'https://docs.example/mcp',
          'secret_id': null,
          'enabled': true,
        },
      });
      await flushToasts(tester);
    });

    testWidgets('the test lists the tools, stores nothing, spins alone', (
      tester,
    ) async {
      final answer = Completer<Object?>();
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: (api) {
          mcpRoutes(api);
          api.on('POST /mcp/test', (_) => answer.future);
        },
      );
      await openForm(tester);
      await tester.enterText(field('Server name'), 'Docs');
      await tester.enterText(field('Server address'), 'http://docs.example');
      await scrollTo(tester, find.text('Test the connection'));
      // Only https addresses.
      await tapAndSettle(tester, find.text('Test the connection'));
      expect(
        find.text('Enter a link that starts with https://'),
        findsOneWidget,
      );
      expect(api.callsTo('POST', '/mcp/test'), isEmpty);
      await flushToasts(tester);
      await tester.enterText(
        field('Server address'),
        'https://docs.example/mcp',
      );
      await tester.tap(find.text('Test the connection'));
      await tester.pump();
      BlockButton button(String label) =>
          tester.widget<BlockButton>(find.widgetWithText(BlockButton, label));
      expect(button('Test the connection').loading, isTrue);
      expect(button('Add the server').loading, isFalse);
      expect(button('Add the server').onPressed, isNull);
      answer.complete({
        'ok': true,
        'tools': ['search', 'fetch', 'save'],
        'writes': ['save'],
        'blocked': [],
        'unsupported': [],
      });
      await tester.pumpAndSettle();
      expect(find.text('The connection works · 3 tools'), findsOneWidget);
      expect(api.callsTo('POST', '/mcp/test').single.body, {
        'url': 'https://docs.example/mcp',
        'token': null,
      });
      expect(api.callsTo('POST', '/mcp'), isEmpty);
      expect(api.callsTo('POST', '/integrations/secrets'), isEmpty);
    });

    testWidgets('stopping a trusted server asks first', (tester) async {
      final api = await pumpPage(tester, const IntegrationsScreen());
      await scrollTo(tester, find.textContaining('Research tools'));
      await tapAndSettle(tester, find.textContaining('Research tools').first);
      await scrollTo(tester, find.text('Stop the server'));
      await tapAndSettle(tester, find.text('Stop the server'));
      expect(find.text('Stop the server?'), findsOneWidget);
      await tapAndSettle(tester, find.text('Cancel'));
      expect(api.callsTo('POST', '/trusted-sources/s-mcp/revoke'), isEmpty);
      await tapAndSettle(tester, find.text('Stop the server'));
      await tapAndSettle(tester, find.text('Stop').last);
      expect(
        api.callsTo('POST', '/trusted-sources/s-mcp/revoke'),
        hasLength(1),
      );
      expect(find.text('The server is stopped'), findsOneWidget);
      await flushToasts(tester);
    });

    testWidgets(
      'a server trusted before its titles were kept reads them once',
      (tester) async {
        final api = await pumpPage(
          tester,
          const IntegrationsScreen(),
          routes: (api) => api
            ..on(
              'GET /capabilities',
              (_) => {
                ...capabilitiesJson,
                'mcp_servers': [
                  for (final s in asJsonList(capabilitiesJson['mcp_servers']))
                    s['connection_id'] == 'm-research'
                        ? {...s, 'tool_titles': {}, 'tool_titles_kept': false}
                        : s,
                ],
              },
            )
            ..on(
              'POST /trusted-sources/mcp/m-research/preview',
              (_) => {
                'id': 'm-research',
                'digest': 'b' * 64,
                'tools': ['search', 'fetch_page', 'save_note'],
                'writes': ['save_note'],
                'blocked': [],
                'titles': {'search': 'Search the web'},
              },
            ),
        );
        await scrollTo(tester, find.textContaining('Research tools'));
        await tapAndSettle(tester, find.textContaining('Research tools').first);
        expect(find.textContaining('Search the web'), findsOneWidget);
        expect(find.textContaining('fetch_page'), findsOneWidget);
        expect(
          api.callsTo('POST', '/trusted-sources/mcp/m-research/preview'),
          hasLength(1),
        );
        // Reading the titles approves nothing.
        expect(api.callsTo('POST', '/trusted-sources/mcp/m-research'), isEmpty);
        expect(find.text('Approve the server'), findsNothing);
      },
    );

    testWidgets('golden MCP sheet light_ar', (tester) async {
      await withRealShadows(() async {
        await pumpPage(
          tester,
          const IntegrationsScreen(),
          locale: 'ar',
          routes: (api) => api.on(
            'POST /trusted-sources/mcp/m-calendar/preview',
            (_) => {
              'id': 'm-calendar',
              'digest': 'a' * 64,
              'tools': ['list_events', 'create_event', 'pay_invoice'],
              'writes': ['create_event'],
              'blocked': ['pay_invoice'],
              'titles': {'list_events': 'عرض المواعيد'},
            },
          ),
        );
        await scrollTo(tester, find.textContaining('Calendar'));
        await tapAndSettle(tester, find.textContaining('Calendar').first);
        await tapAndSettle(tester, find.text('مراجعة الأدوات'));
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/mcp_sheet_light_ar.png'),
        );
      });
    });
  });

  group('news and channels', () {
    testWidgets('a domain is checked before it is sent', (tester) async {
      final api = await pumpPage(tester, const IntegrationsScreen());
      await scrollTo(tester, find.text('News domains'));
      await tapAndSettle(tester, find.text('News domains'));
      await tester.enterText(find.byType(EditableText), 'not a domain');
      await tapAndSettle(tester, find.text('Add'));
      expect(
        find.text('Enter a valid domain like example.com'),
        findsOneWidget,
      );
      expect(api.callsTo('POST', '/trusted-sources'), isEmpty);
      await flushToasts(tester);
      await tester.enterText(
        find.byType(EditableText),
        'https://Example.com/markets',
      );
      await tapAndSettle(tester, find.text('Add'));
      expect(api.callsTo('POST', '/trusted-sources').single.body, {
        'kind': 'feed_domain',
        'identifier': 'example.com',
      });
      expect(
        tester.widget<EditableText>(find.byType(EditableText)).controller.text,
        isEmpty,
      );
    });

    testWidgets('a feed link is checked before it is sent', (tester) async {
      final api = await pumpPage(tester, const IntegrationsScreen());
      await scrollTo(tester, find.text('RSS feeds'));
      await tapAndSettle(tester, find.text('RSS feeds'));
      await tester.enterText(find.byType(EditableText), 'feeds.example.com');
      await tapAndSettle(tester, find.text('Add'));
      expect(
        find.text('Enter a link that starts with https://'),
        findsOneWidget,
      );
      expect(api.callsTo('POST', '/integrations'), isEmpty);
      await flushToasts(tester);
      await tester.enterText(
        find.byType(EditableText),
        'https://feeds.example.com/rss.xml',
      );
      await tapAndSettle(tester, find.text('Add'));
      expect(api.callsTo('POST', '/integrations').single.body, {
        'payload': {
          'type': 'news_feed',
          'name': 'feeds.example.com',
          'url': 'https://feeds.example.com/rss.xml',
          'enabled': true,
        },
      });
    });

    void unlinkedTelegram(QueryApi api) => api
      ..on(
        'GET /capabilities',
        (_) => {
          ...capabilitiesJson,
          'integrations': [
            for (final i in asJsonList(capabilitiesJson['integrations']))
              if (i['type'] != 'telegram') i,
          ],
        },
      )
      ..on('POST /integrations/secrets', (_) => {'id': 'sec-tg'})
      ..on('POST /integrations', (_) => {'id': 'i-tg'});

    testWidgets('Telegram: the bot token is stored first, then the link', (
      tester,
    ) async {
      const token = '123456789:AAH-test-bot-token';
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: unlinkedTelegram,
      );
      await scrollTo(tester, find.text('Telegram'));
      expect(find.textContaining('Not linked'), findsOneWidget);
      await tapAndSettle(tester, find.text('Telegram'));
      expect(find.text('Link Telegram'), findsOneWidget);
      final field = find.byType(EditableText);
      expect(tester.widget<EditableText>(field).obscureText, isTrue);
      // Too short: nothing leaves the phone.
      await tester.enterText(field, 'short');
      await tapAndSettle(tester, find.text('Save'));
      expect(find.text('The value is too short'), findsOneWidget);
      expect(api.callsTo('POST', '/integrations/secrets'), isEmpty);
      await flushToasts(tester);
      await tester.enterText(field, token);
      await tapAndSettle(tester, find.text('Save'));
      expect(api.callsTo('POST', '/integrations/secrets').single.body, {
        'name': 'telegram-bot',
        'value': token,
      });
      final link = api.callsTo('POST', '/integrations').single;
      expect(link.body, {
        'payload': {
          'type': 'telegram',
          'name': 'Telegram',
          'secret_id': 'sec-tg',
          // The personal agent receives the owner's Telegram messages by default.
          'deliver_to_agent_id': 'a-lonora',
          'enabled': true,
        },
      });
      expect(
        order(api, 'POST', '/integrations/secrets'),
        lessThan(order(api, 'POST', '/integrations')),
      );
      expect(find.text('Link Telegram'), findsNothing);
      expect(find.text('Saved securely'), findsOneWidget);
      expect(screenText(tester), isNot(contains(token)));
      await flushToasts(tester);
    });

    testWidgets('Telegram: messages can reach another agent', (tester) async {
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: unlinkedTelegram,
      );
      await scrollTo(tester, find.text('Telegram'));
      await tapAndSettle(tester, find.text('Telegram'));
      await tester.enterText(find.byType(EditableText), 'bot-token-0123456');
      await tapAndSettle(tester, find.text('Research Desk'));
      await tapAndSettle(tester, find.text('Save'));
      expect(
        asJson(
          asJson(api.callsTo('POST', '/integrations').single.body)['payload'],
        )['deliver_to_agent_id'],
        'a-research',
      );
      await flushToasts(tester);
    });
  });

  group('saved secrets', () {
    testWidgets(
      'a secret is deleted after a confirmation; a used one is refused',
      (tester) async {
        var inUse = true;
        final api = await pumpPage(
          tester,
          const IntegrationsScreen(),
          routes: (api) => api.on('DELETE /secrets/sec-gh', (_) {
            if (inUse) throw ApiError(status: 409, code: 'secret_in_use');
            return {'deleted': true};
          }),
        );
        await scrollTo(tester, find.textContaining('GITHUB_TOKEN'));
        final semantics = tester.ensureSemantics();
        // The delete action is its own node with an action label (not the confirmation's
        // question) and the tap; the row reads its name and its date.
        final action = tester.getSemantics(find.byIcon(FIcons.trash2));
        expect(
          action,
          isSemantics(
            label: 'Delete «GITHUB_TOKEN»',
            isButton: true,
            hasTapAction: true,
          ),
        );
        expect(
          tester.getSemantics(find.textContaining('GITHUB_TOKEN').first).label,
          allOf(contains('GITHUB_TOKEN'), isNot(contains('Delete'))),
        );
        semantics.dispose();
        await tapAndSettle(tester, find.byIcon(FIcons.trash2));
        expect(find.textContaining('GITHUB_TOKEN\u2069»?'), findsOneWidget);
        expect(
          find.textContaining('workspace commands loses it'),
          findsOneWidget,
        );
        await tapAndSettle(tester, find.text('Cancel'));
        expect(api.callsTo('DELETE', '/secrets/sec-gh'), isEmpty);
        await tapAndSettle(tester, find.byIcon(FIcons.trash2));
        await tapAndSettle(tester, find.text('Delete'));
        expect(api.callsTo('DELETE', '/secrets/sec-gh'), hasLength(1));
        expect(
          find.text('A connection uses this secret, so it cannot be deleted.'),
          findsOneWidget,
        );
        await flushToasts(tester);
        inUse = false;
        final reads = api.callsTo('GET', '/secrets').length;
        await tapAndSettle(tester, find.byIcon(FIcons.trash2));
        await tapAndSettle(tester, find.text('Delete'));
        expect(api.callsTo('DELETE', '/secrets/sec-gh'), hasLength(2));
        expect(
          find.textContaining('GITHUB_TOKEN\u2069» deleted'),
          findsOneWidget,
        );
        expect(api.callsTo('GET', '/secrets').length, reads + 1);
        await flushToasts(tester);
      },
    );
  });

  testWidgets('a change while another page covers this one is read on return', (
    tester,
  ) async {
    final api = await setUpExtServices(integrationsRoutes);
    final store = extStore(agents: agents);
    final feed = ScriptedRealtime(store);
    realtime = feed;
    await pumpExt(tester, store, const IntegrationsScreen());
    int reads() => api.callsTo('GET', '/capabilities').length;
    final first = reads();
    feed.emit('trusted_source.updated');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(reads(), first + 1);
    await tapAndSettle(tester, find.text('Global model routing'));
    expect(find.text('stub:/settings/models'), findsOneWidget);
    feed.emit('mcp.updated');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(reads(), first + 1);
    Navigator.of(tester.element(find.byType(StubPage))).pop();
    await tester.pumpAndSettle();
    expect(reads(), first + 2);
    // Nothing changed while away: coming back again reads nothing.
    await tapAndSettle(tester, find.text('Global model routing'));
    Navigator.of(tester.element(find.byType(StubPage))).pop();
    await tester.pumpAndSettle();
    expect(reads(), first + 2);
  });

  group('failures', () {
    testWidgets('a failed accounts read says so with a retry', (tester) async {
      var fail = true;
      final api = await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: (api) => api.on('GET /trading/connections', (_) {
          if (fail) throw ApiError.network();
          return connectionsJson;
        }),
      );
      expect(find.textContaining('Could not connect'), findsOneWidget);
      expect(find.textContaining('Exness'), findsNothing);
      // The page still shows the rest.
      expect(find.text('Model providers'), findsOneWidget);
      fail = false;
      await tapAndSettle(tester, find.text('Retry'));
      expect(api.callsTo('GET', '/trading/connections'), hasLength(2));
      expect(find.textContaining('Exness'), findsOneWidget);
      expect(find.textContaining('Could not connect'), findsNothing);
    });

    testWidgets('a failed pull keeps the page and says so', (tester) async {
      var fail = false;
      await pumpPage(
        tester,
        const IntegrationsScreen(),
        routes: (api) => api.on('GET /capabilities', (_) {
          if (fail) throw ApiError.network();
          return capabilitiesJson;
        }),
      );
      fail = true;
      await tester.fling(pageScrollable, const Offset(0, 400), 1000);
      await tester.pumpAndSettle();
      expect(find.textContaining('Could not connect'), findsOneWidget);
      await scrollTo(tester, find.textContaining('Research tools'));
      expect(find.textContaining('Research tools'), findsOneWidget);
      await flushToasts(tester);
    });
  });

  group('ChatGPT plan', () {
    for (final revoked in [true, false]) {
      testWidgets('signing out asks first (revoked: $revoked)', (tester) async {
        final api = await pumpPage(
          tester,
          const ProvidersPage(),
          routes: (api) => api.on(
            'POST /providers/openai_chatgpt/sign-out',
            (_) => {'signed_out': true, 'revoked': revoked},
          ),
        );
        await tapAndSettle(tester, find.text('Sign out'));
        expect(find.text('Sign out of ChatGPT?'), findsOneWidget);
        await tapAndSettle(tester, find.text('Cancel'));
        expect(
          api.callsTo('POST', '/providers/openai_chatgpt/sign-out'),
          isEmpty,
        );
        await tapAndSettle(tester, find.text('Sign out'));
        await tapAndSettle(tester, find.text('Sign out').last);
        expect(
          api.callsTo('POST', '/providers/openai_chatgpt/sign-out'),
          hasLength(1),
        );
        if (revoked) {
          expect(
            find.text('Signed out. Lonora no longer uses your ChatGPT plan.'),
            findsOneWidget,
          );
          expect(toastIcon(FIcons.check), findsOneWidget);
        } else {
          // Not confirmed revoked: a notice, not a success.
          expect(toastIcon(FIcons.info), findsOneWidget);
          expect(toastIcon(FIcons.check), findsNothing);
        }
        expect(api.callsTo('GET', '/providers'), hasLength(2));
        await flushToasts(tester);
      });
    }
  });

  group('simulation snapshot', () {
    void needsSnapshot(QueryApi api) {
      var imported = false;
      api
        ..on('GET /trading/accounts/c-sim', (_) {
          if (!imported) {
            throw ApiError(status: 409, code: 'simulation_snapshot_required');
          }
          return {
            'account': {'balance': '5000', 'currency': 'USD'},
          };
        })
        ..on('GET /market/symbols', (_) => ['XAUUSD'])
        ..on('POST /trading/connections/c-sim/simulation', (_) {
          imported = true;
          return {'ok': true};
        });
    }

    testWidgets('a JSON snapshot is imported', (tester) async {
      final picker = FakeFilePicker([
        MemoryPickedFile('snapshot.json', '{"balance": 5000, "symbols": []}'),
      ]);
      FilePickerPlatform.instance = picker;
      final api = await pumpPage(
        tester,
        const BrokerAccountPage(connectionId: 'c-sim'),
        routes: needsSnapshot,
      );
      expect(
        find.text('Import a market snapshot before using the simulation.'),
        findsNothing,
      );
      await tapAndSettle(tester, find.text('Import the simulation data'));
      expect(picker.asked.single, ['json']);
      expect(
        api
            .callsTo('POST', '/trading/connections/c-sim/simulation')
            .single
            .body,
        {
          'snapshot': {'balance': 5000, 'symbols': []},
        },
      );
      expect(find.text('The simulation data is imported'), findsOneWidget);
      expect(find.textContaining('5,000.00 USD'), findsOneWidget);
      // Never an order path.
      expect(api.calls.where((c) => c.path.contains('execute')), isEmpty);
      await flushToasts(tester);
    });

    testWidgets('a file that is not JSON is refused before sending', (
      tester,
    ) async {
      FilePickerPlatform.instance = FakeFilePicker([
        MemoryPickedFile('snapshot.json', 'balance = 5000'),
      ]);
      final api = await pumpPage(
        tester,
        const BrokerAccountPage(connectionId: 'c-sim'),
        routes: needsSnapshot,
      );
      await tapAndSettle(tester, find.text('Import the simulation data'));
      expect(find.text('The file is not valid JSON.'), findsOneWidget);
      expect(
        api.callsTo('POST', '/trading/connections/c-sim/simulation'),
        isEmpty,
      );
      await flushToasts(tester);
    });

    testWidgets('a cancelled pick sends nothing', (tester) async {
      FilePickerPlatform.instance = FakeFilePicker(const []);
      final api = await pumpPage(
        tester,
        const BrokerAccountPage(connectionId: 'c-sim'),
        routes: needsSnapshot,
      );
      await tapAndSettle(tester, find.text('Import the simulation data'));
      expect(
        api.callsTo('POST', '/trading/connections/c-sim/simulation'),
        isEmpty,
      );
      expect(find.text('Import the simulation data'), findsOneWidget);
    });
  });

  group('fields and row actions', () {
    /// The [index]th field on screen: its input flags and the direction its text reads in.
    ({TextField field, TextDirection direction}) fieldAt(
      WidgetTester tester,
      int index,
    ) {
      final editable = find.byType(EditableText).at(index);
      return (
        field: tester.widget<TextField>(
          find.ancestor(of: editable, matching: find.byType(TextField)),
        ),
        direction: tester
            .state<EditableTextState>(editable)
            .renderEditable
            .textDirection,
      );
    }

    void expectLtrUncorrected(WidgetTester tester, int index) {
      final f = fieldAt(tester, index);
      expect(f.direction, TextDirection.ltr, reason: 'field $index');
      expect(f.field.autocorrect, isFalse, reason: 'field $index');
    }

    void expectSecretInput(WidgetTester tester, int index) {
      expectLtrUncorrected(tester, index);
      final f = fieldAt(tester, index).field;
      expect(f.enableSuggestions, isFalse, reason: 'field $index');
      expect(f.enableIMEPersonalizedLearning, isFalse, reason: 'field $index');
    }

    testWidgets('broker account and region read left to right; the key is '
        'write-only input', (tester) async {
      await pumpPage(tester, const BrokerFormPage(), locale: 'ar');
      // MetaApi: account number, API key, region.
      expect(find.byType(EditableText), findsNWidgets(3));
      expectLtrUncorrected(tester, 0);
      expectSecretInput(tester, 1);
      expectLtrUncorrected(tester, 2);
    });

    testWidgets('K11 an Arabic hint stays under its label, the text reads '
        'left to right', (tester) async {
      await pumpPage(tester, const BrokerFormPage(), locale: 'ar');
      final account = fieldAt(tester, 0).field;
      expect(account.decoration!.hintText, 'مثل: 7310');
      expect(account.decoration!.hintTextDirection, TextDirection.rtl);
      expect(account.textDirection, TextDirection.ltr);
      expect(
        fieldAt(tester, 1).field.decoration!.hintTextDirection,
        TextDirection.rtl,
      );
    });

    testWidgets('the key\'s eye is a button with the tap action', (
      tester,
    ) async {
      await pumpPage(tester, const BrokerFormPage());
      final semantics = tester.ensureSemantics();
      expect(
        tester.getSemantics(find.byIcon(FIcons.eye)),
        isSemantics(
          label: 'Show the key',
          isButton: true,
          hasTapAction: true,
          hasToggledState: true,
          isToggled: false,
        ),
      );
      tester.semantics.tap(find.semantics.byLabel('Show the key'));
      await tester.pumpAndSettle();
      expect(fieldAt(tester, 1).field.obscureText, isFalse);
      expect(
        tester.getSemantics(find.byIcon(FIcons.eyeOff)),
        isSemantics(label: 'Hide the key', hasTapAction: true, isToggled: true),
      );
      semantics.dispose();
    });

    testWidgets('the MCP address reads left to right; the token is '
        'write-only input', (tester) async {
      await pumpPage(tester, const McpFormPage(), locale: 'ar');
      await tapAndSettle(tester, find.text('رمز الوصول'));
      // Name, address, token.
      expect(find.byType(EditableText), findsNWidgets(3));
      expect(fieldAt(tester, 0).direction, TextDirection.rtl);
      expectLtrUncorrected(tester, 1);
      expectSecretInput(tester, 2);
    });

    testWidgets('a news domain: the field reads left to right, Remove is its '
        'own button', (tester) async {
      await pumpPage(tester, const IntegrationsScreen(), locale: 'ar');
      await scrollTo(tester, find.text('نطاقات الأخبار'));
      await tapAndSettle(tester, find.text('نطاقات الأخبار'));
      expectLtrUncorrected(tester, 0);
      final semantics = tester.ensureSemantics();
      final remove = tester.getSemantics(find.byIcon(FIcons.x).first);
      expect(remove, isSemantics(isButton: true, hasTapAction: true));
      expect(remove.label, contains('reuters.com'));
      expect(
        tester.getSemantics(find.textContaining('reuters.com').first),
        isNot(same(remove)),
      );
      semantics.dispose();
    });

    testWidgets('rows that open a page use the kit\'s own chevron', (
      tester,
    ) async {
      await pumpPage(tester, const IntegrationsScreen());
      for (final title in [
        'Add a trading account',
        'Model providers',
        'Global model routing',
        'Add an MCP server',
      ]) {
        await scrollTo(tester, find.text(title));
        final row = find.ancestor(
          of: find.text(title),
          matching: find.byType(LnListTile),
        );
        expect(tester.widget<LnListTile>(row).trailing, isNull, reason: title);
        expect(
          find.descendant(of: row, matching: find.byIcon(FIcons.chevronRight)),
          findsOneWidget,
          reason: title,
        );
      }
    });
  });
}
