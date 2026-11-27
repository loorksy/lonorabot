// Models, usage and «What is running»: what they read, what they write, live updates, and the
// goldens (light/dark × ar/en at 393×852, DPR 2).
//
// Regenerate goldens with: flutter test --update-goldens test/features/settings_ext
import 'package:fl_chart/fl_chart.dart' show BarChart;
import 'package:flutter/semantics.dart' show SemanticsAction;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:forui/forui.dart' show FIcons, FTheme, FTile;
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/design/design.dart'
    show BlockButton, LnListTile, LnSize, LnSpace;
import 'package:lonora/features/settings/integrations/ext_common.dart'
    show PillButton;
import 'package:lonora/features/settings/models_screen.dart';
import 'package:lonora/features/settings/running_screen.dart';
import 'package:lonora/features/settings/usage/usage_widgets.dart'
    show UsageChartCard;
import 'package:lonora/features/settings/usage_screen.dart';
import 'package:lonora/l10n/l10n.dart' show formatDate;
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart' show ApplyEventAction;

import '../../design/harness.dart';
import 'ext_harness.dart';
import 'fixtures.dart';

void main() {
  setUpAll(setUpExtTests);

  Future<void> flushToasts(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  }

  BlockButton blockButton(WidgetTester tester, String label) =>
      tester.widget<BlockButton>(find.widgetWithText(BlockButton, label));

  /// Pulls the page down past the refresh trigger and lets the reads finish.
  Future<void> pullToRefresh(WidgetTester tester) async {
    await tester.fling(pageScrollable, const Offset(0, 400), 1000);
    await tester.pumpAndSettle();
  }

  group('models', () {
    Future<QueryApi> pumpModels(
      WidgetTester tester, {
      String locale = 'en',
      AppThemeMode theme = AppThemeMode.light,
      void Function(QueryApi api)? routes,
    }) async {
      final api = await setUpExtServices((api) {
        modelsRoutes(api);
        routes?.call(api);
      });
      final store = extStore(locale: locale, theme: theme, agents: agents);
      await pumpExt(tester, store, const ModelsScreen());
      return api;
    }

    testWidgets('rows that open a picker or page use the kit\'s own chevron', (
      tester,
    ) async {
      await pumpModels(tester);
      void expectKitChevrons() {
        final rows = find.byWidgetPredicate(
          (w) => w is LnListTile && w.onTap != null,
        );
        expect(rows, findsWidgets);
        for (var i = 0; i < rows.evaluate().length; i++) {
          final row = rows.at(i);
          expect(tester.widget<LnListTile>(row).trailing, isNull);
          expect(
            find.descendant(
              of: row,
              matching: find.byIcon(FIcons.chevronRight),
            ),
            findsOneWidget,
          );
        }
      }

      expectKitChevrons();
      await scrollTo(tester, find.text('Model providers'));
      expectKitChevrons();
    });

    testWidgets('shows the routing, each agent model and the lists', (
      tester,
    ) async {
      await pumpModels(tester);
      expect(find.text('One model for text work'), findsOneWidget);
      expect(find.textContaining('OpenAI · GPT-5'), findsWidgets);
      expect(find.textContaining('gpt-live-1'), findsOneWidget);
      // Save is enabled only once something changed.
      expect(blockButton(tester, 'Save global routing').onPressed, isNull);
      await tapAndSettle(tester, find.text('Route by capability'));
      expect(blockButton(tester, 'Save global routing').onPressed, isNotNull);
      await tapAndSettle(tester, find.text('One model for text work'));
      expect(blockButton(tester, 'Save global routing').onPressed, isNull);
      await scrollTo(tester, find.textContaining('Chosen by you'));
      expect(find.textContaining('Chosen by you'), findsOneWidget);
      await scrollTo(tester, find.textContaining('Available models'));
      expect(find.textContaining('Available models (5)'), findsOneWidget);
      expect(find.text('Capabilities unverified'), findsOneWidget);
    });

    testWidgets('ms:C15 the default model starts its line in sentence case', (
      tester,
    ) async {
      await pumpModels(tester);
      await scrollTo(tester, find.text('Your default model'));
      expect(find.text('Your default model'), findsOneWidget);
      expect(find.text('your default model'), findsNothing);
    });

    testWidgets('ms:C9 «global» is the catalog\'s «العام» in Arabic', (
      tester,
    ) async {
      await pumpModels(tester, locale: 'ar');
      expect(find.text('التوجيه العام'), findsOneWidget);
      expect(find.textContaining('العالمي'), findsNothing);
    });

    testWidgets('routing by capability is saved after a confirmation', (
      tester,
    ) async {
      final api = await pumpModels(
        tester,
        routes: (api) => api.on('PUT /settings/models', (body) => body),
      );
      await tapAndSettle(tester, find.text('Route by capability'));
      expect(find.text('Conversation'), findsOneWidget);
      await tapAndSettle(tester, find.text('Vision'));
      // A model that cannot read images is not offered for Vision.
      expect(find.textContaining('GPT-4\u2069'), findsNothing);
      expect(find.textContaining('Claude Experimental'), findsOneWidget);
      await tapAndSettle(tester, find.textContaining('Claude Opus 5'));
      await scrollTo(tester, find.text('Save global routing'));
      await tapAndSettle(tester, find.text('Save global routing'));
      expect(find.text('Save the global routing?'), findsOneWidget);
      await tapAndSettle(tester, find.text('Save'));
      final put = api.callsTo('PUT', '/settings/models').single;
      expect(put.body, {
        'mode': 'custom',
        'unified': {'provider': 'openai', 'model': 'gpt-5'},
        'routes': {
          'realtime_voice': {'provider': 'openai', 'model': 'gpt-live-1'},
          'vision': {'provider': 'anthropic', 'model': 'claude-opus-5'},
        },
      });
      await flushToasts(tester);
    });

    testWidgets('a cleared choice no longer reads as chosen by you', (
      tester,
    ) async {
      await pumpModels(
        tester,
        routes: (api) => api.on(
          'GET /agents/a-gold/model/summary',
          (_) => {
            'record': {
              'revision': 3,
              'preference': {'primary': null, 'fallbacks': []},
              'chosen_by': 'owner',
            },
            'current': {
              'provider': 'openai',
              'model': 'gpt-5',
              'name': 'GPT-5',
            },
          },
        ),
      );
      await scrollTo(tester, find.textContaining('Research Desk'));
      expect(find.textContaining('Chosen by you'), findsNothing);
      // The personal agent still inherits its chosen model.
      expect(
        find.textContaining("Lonora's model when it was created"),
        findsOneWidget,
      );
    });

    testWidgets('a refresh keeps an unsaved routing change', (tester) async {
      final api = await pumpModels(tester);
      await tapAndSettle(tester, find.text('Route by capability'));
      await pullToRefresh(tester);
      expect(api.callsTo('GET', '/settings/models'), hasLength(2));
      expect(find.text('Conversation'), findsOneWidget);
      expect(blockButton(tester, 'Save global routing').onPressed, isNotNull);
    });

    testWidgets('without a model list the routing is only shown', (
      tester,
    ) async {
      final api = await pumpModels(
        tester,
        routes: (api) => api.on(
          'GET /providers',
          (_) => [
            for (final p in providersJson) {...p, 'configured': false},
          ],
        ),
      );
      expect(
        find.text('Models appear here after you add a model provider.'),
        findsOneWidget,
      );
      expect(find.text('Mode'), findsOneWidget);
      expect(find.text('Route by capability'), findsNothing);
      expect(find.text('Save global routing'), findsNothing);
      // The only global model cannot be cleared: its row opens no picker.
      await tapAndSettle(tester, find.text('Unified model'));
      expect(find.text('Unified model'), findsOneWidget);
      expect(api.callsTo('PUT', '/settings/models'), isEmpty);
      // The way to a provider stays.
      await scrollTo(tester, find.text('Model providers'));
      expect(find.text('Model providers'), findsOneWidget);
    });

    testWidgets('an agent row opens its settings', (tester) async {
      await pumpModels(tester);
      await scrollTo(tester, find.textContaining('Research Desk'));
      await tapAndSettle(tester, find.textContaining('Research Desk'));
      expect(find.text('stub:/agent/a-research/settings'), findsOneWidget);
    });

    testWidgets('offline read offers a retry', (tester) async {
      await pumpModels(
        tester,
        routes: (api) =>
            api.on('GET /settings/models', (_) => throw ApiError.network()),
      );
      expect(find.text('Retry'), findsOneWidget);
    });

    for (final v in goldenVariants) {
      testWidgets('golden ${v.name}', (tester) async {
        await withRealShadows(() async {
          await pumpModels(tester, locale: v.locale, theme: v.theme);
          await expectLater(
            find.byType(WidgetsApp),
            matchesGoldenFile('goldens/models_${v.name}.png'),
          );
        });
      });
    }
  });

  group('usage', () {
    Future<QueryApi> pumpUsage(
      WidgetTester tester, {
      String locale = 'en',
      AppThemeMode theme = AppThemeMode.light,
      void Function(QueryApi api)? routes,
    }) async {
      final api = await setUpExtServices((api) {
        usageRoutes(api);
        routes?.call(api);
      });
      final store = extStore(locale: locale, theme: theme, agents: agents);
      await pumpExt(tester, store, const UsageScreen());
      return api;
    }

    testWidgets('reads 30 days in the owner zone and shows cost and change', (
      tester,
    ) async {
      final api = await pumpUsage(tester);
      // No zone is sent (as on the Web): the server uses the owner's stored zone.
      final series = api.gets.firstWhere((g) => g.path == '/usage/series');
      expect(series.query, {'period': 'month'});
      expect(api.gets.firstWhere((g) => g.path == '/usage/rank').query, {
        'period': 'month',
      });
      expect(find.text(r'$12.47'), findsOneWidget);
      expect(find.text('Cost · the last 30 days'), findsOneWidget);
      expect(find.textContaining('27%'), findsOneWidget);
      expect(find.text('November so far'), findsOneWidget);
      expect(find.textContaining('No spending cap'), findsOneWidget);
      await scrollTo(tester, find.text('By agent'));
      expect(find.textContaining('متداول الذهب'), findsOneWidget);
      await scrollTo(tester, find.text('By model'));
      expect(find.textContaining('claude-opus-5'), findsOneWidget);
      await scrollTo(tester, find.text('All time'));
      expect(find.textContaining('18.4M'), findsOneWidget);
    });

    testWidgets('the period switch reads today by the hour', (tester) async {
      final api = await pumpUsage(
        tester,
        routes: (api) => api.on(
          'GET /usage/series',
          (_) => seriesJson(
            period:
                api.gets
                        .lastWhere((g) => g.path == '/usage/series')
                        .query?['period']
                    as String? ??
                'month',
          ),
        ),
      );
      final calls = <MethodCall>[];
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, (call) async {
            calls.add(call);
            return null;
          });
      await tapAndSettle(tester, find.text('Today').first);
      expect(
        api.gets.where((g) => g.path == '/usage/series').last.query?['period'],
        'day',
      );
      expect(find.text('Cost · today so far'), findsOneWidget);
      expect(find.textContaining('now'), findsOneWidget);
      expect(
        calls.where((c) => c.arguments == 'HapticFeedbackType.selectionClick'),
        isNotEmpty,
      );
    });

    testWidgets('the chart table lists the days, newest first', (tester) async {
      await pumpUsage(tester);
      await tapAndSettle(tester, find.byIcon(FIcons.table));
      expect(find.text('Cost'), findsOneWidget);
      expect(find.text('Tokens'), findsWidgets);
      double top(String text) => tester.getTopLeft(find.text(text).last).dy;
      final rows = [
        'Day',
        'Today · Friday 27 November',
        'Yesterday · Thursday 26 November',
        'Wednesday 25 November',
        'Tuesday 24 November',
      ];
      for (var i = 1; i < rows.length; i++) {
        expect(top(rows[i]), greaterThan(top(rows[i - 1])), reason: rows[i]);
      }
      // Thirty days, each once.
      expect(find.textContaining('November'), findsWidgets);
      await scrollTo(tester, find.text('Thursday 29 October'));
      expect(find.text('Thursday 29 October'), findsOneWidget);
      expect(top('Thursday 29 October'), greaterThan(top('Friday 30 October')));
    });

    testWidgets('the chart/table switch is a button with the tap action', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await pumpUsage(tester);
      expect(
        tester.getSemantics(find.byIcon(FIcons.table)),
        isSemantics(
          label: 'Show as a table',
          isButton: true,
          hasTapAction: true,
          hasToggledState: true,
          isToggled: false,
        ),
      );
      tester.semantics.tap(find.semantics.byLabel('Show as a table'));
      await tester.pumpAndSettle();
      expect(find.text('Day'), findsOneWidget);
      expect(
        tester.getSemantics(find.byIcon(FIcons.chartColumn)),
        isSemantics(
          label: 'Show as a chart',
          isButton: true,
          hasTapAction: true,
          hasToggledState: true,
          isToggled: true,
        ),
      );
      semantics.dispose();
    });

    for (final locale in ['ar', 'en']) {
      testWidgets('the dates sit under the bars, clear of the axis ($locale)', (
        tester,
      ) async {
        await pumpUsage(tester, locale: locale);
        final chart = tester.getRect(find.byType(BarChart));
        Finder label(String text) => find.descendant(
          of: find.byType(UsageChartCard),
          matching: find.text(text),
        );
        final today = tester.getRect(label(locale == 'ar' ? 'اليوم' : 'Today'));
        final oldest = tester.getRect(
          label(formatDate('d MMMM', locale, DateTime.utc(2026, 10, 29))),
        );
        // The dollar axis takes 44 dp on the start side; today's bar is at the far end.
        if (locale == 'ar') {
          expect(today.left, moreOrLessEquals(chart.left, epsilon: 1));
          expect(oldest.right, lessThanOrEqualTo(chart.right - 43));
        } else {
          expect(today.right, moreOrLessEquals(chart.right, epsilon: 1));
          expect(oldest.left, greaterThanOrEqualTo(chart.left + 43));
        }
      });
    }

    testWidgets('a failed refresh keeps the figures and says so', (
      tester,
    ) async {
      var fail = false;
      await pumpUsage(
        tester,
        routes: (api) => api.on('GET /usage/series', (_) {
          if (fail) throw ApiError.network();
          return seriesJson();
        }),
      );
      fail = true;
      await pullToRefresh(tester);
      expect(find.text(r'$12.47'), findsOneWidget);
      expect(find.textContaining('Could not connect'), findsOneWidget);
      await flushToasts(tester);
    });

    testWidgets('an agent no longer listed reads by its ranked name', (
      tester,
    ) async {
      await pumpUsage(
        tester,
        routes: (api) => api.on(
          'GET /usage/rank',
          (_) => {
            ...rankJson,
            'agents': [
              {
                'agent_id': 'a-old',
                'agent_name': 'Old Desk',
                'cost_usd': 7.9,
                'tokens': 1100000,
                'requests': 800,
                'unpriced_requests': 0,
              },
            ],
          },
        ),
      );
      await scrollTo(tester, find.textContaining('Old Desk'));
      await tapAndSettle(tester, find.textContaining('Old Desk'));
      expect(find.text('Usage details'), findsOneWidget);
      expect(find.textContaining('Old Desk'), findsOneWidget);
      expect(find.text('Lonora'), findsNothing);
      expect(find.textContaining('of the total'), findsOneWidget);
    });

    testWidgets('ms:C10 the unpriced count takes the Arabic plural', (
      tester,
    ) async {
      await pumpUsage(tester, locale: 'ar');
      expect(find.text('12 طلبًا دون سعر معلن'), findsOneWidget);
      expect(find.textContaining('طلبات دون'), findsNothing);
    });

    testWidgets('ms:C5 a row without a chevron keeps the rows\' grid', (
      tester,
    ) async {
      await pumpUsage(tester);
      await scrollTo(tester, find.text('3%'));
      // The two agent rows open their usage; the unnamed one does not.
      final rights = {
        for (final pct in ['63%', '34%', '3%'])
          tester.getRect(find.text(pct)).right,
      };
      expect(rights, hasLength(1));
    });

    testWidgets('an agent opens its own usage with its share', (tester) async {
      final api = await pumpUsage(tester);
      await scrollTo(tester, find.textContaining('متداول الذهب'));
      await tapAndSettle(tester, find.textContaining('متداول الذهب'));
      expect(find.text('Usage details'), findsOneWidget);
      expect(
        api.gets.where((g) => g.query?['agent_id'] == 'a-gold'),
        hasLength(2),
      );
      expect(find.textContaining('of the total'), findsOneWidget);
    });

    testWidgets('CSV export downloads the period and opens the share sheet', (
      tester,
    ) async {
      final shares = <MethodCall>[];
      mockExportChannels(shares);
      final api = await pumpUsage(tester);
      await scrollTo(tester, find.text('Export CSV'));
      await tapAndSettle(tester, find.text('Export CSV'));
      final download = api.downloads.single;
      expect(download.path, '/usage/export.csv');
      expect(download.query, {'period': 'month'});
      expect(download.savePath, endsWith('lonora-usage-month.csv'));
      expect(shares, hasLength(1));
    });

    for (final v in goldenVariants) {
      testWidgets('golden ${v.name}', (tester) async {
        await withRealShadows(() async {
          await pumpUsage(tester, locale: v.locale, theme: v.theme);
          await expectLater(
            find.byType(WidgetsApp),
            matchesGoldenFile('goldens/usage_${v.name}.png'),
          );
        });
      });
    }

    testWidgets('golden chart and KPIs dark_ar', (tester) async {
      await withRealShadows(() async {
        await pumpUsage(tester, locale: 'ar', theme: AppThemeMode.dark);
        await tester.drag(pageScrollable, const Offset(0, -520));
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/usage_chart_dark_ar.png'),
        );
      });
    });
  });

  group('what is running', () {
    Future<(QueryApi, dynamic)> pumpRunning(
      WidgetTester tester, {
      String locale = 'en',
      AppThemeMode theme = AppThemeMode.light,
      Json? running,
      List<Json>? runs,
      void Function(QueryApi api)? routes,
    }) async {
      final runList = runs ?? [for (final r in activeRuns()) r.raw];
      final api = await setUpExtServices((api) {
        api
          ..on('GET /workspace/running', (_) => running ?? runningJson)
          ..on('GET /runs', (_) => runList);
        routes?.call(api);
      });
      final store = extStore(
        locale: locale,
        theme: theme,
        agents: agents,
        runs: activeRuns(),
      );
      await pumpExt(tester, store, const RunningScreen());
      return (api, store);
    }

    testWidgets('lists the agents at work and the workspace processes', (
      tester,
    ) async {
      final (api, _) = await pumpRunning(tester);
      // Two runs in progress (the child of r-2 and the finished run are left out).
      expect(find.textContaining('متداول الذهب'), findsWidgets);
      expect(find.textContaining('Waiting for your reply'), findsOneWidget);
      expect(find.textContaining('Research Desk'), findsWidgets);
      expect(find.text('Stopping…'), findsOneWidget);
      await scrollTo(tester, find.textContaining('backtest.py'));
      expect(find.textContaining('python backtest.py'), findsOneWidget);
      expect(api.callsTo('GET', '/runs'), hasLength(1));
    });

    testWidgets('ms:C15 «today» reads mid-sentence in lower case', (
      tester,
    ) async {
      final now = DateTime.now().toUtc().toIso8601String();
      await pumpRunning(
        tester,
        running: {
          ...runningJson,
          'processes': [
            {...asJsonList(runningJson['processes']).first, 'started_at': now},
          ],
        },
      );
      await scrollTo(tester, find.textContaining('backtest.py'));
      expect(find.textContaining('Started today '), findsOneWidget);
      expect(find.textContaining('Started Today'), findsNothing);
    });

    testWidgets('ms:C12 the closing note is in the section footers\' style', (
      tester,
    ) async {
      await pumpRunning(tester);
      final note = find.text(
        'Every process your agents run in the workspace, with the agent that '
        'started it.',
      );
      await scrollTo(tester, note);
      final footer = FTheme.of(tester.element(note))
          .tileGroupStyle
          .descriptionTextStyle
          .resolve(const {});
      expect(tester.widget<Text>(note).style, footer);
      final page = tester.getRect(find.byType(RunningScreen));
      expect(tester.getRect(note).left - page.left, LnSpace.pageGutter);
    });

    testWidgets('every run and process row is at least 48 dp', (tester) async {
      await pumpRunning(tester);
      Future<void> expectRows() async {
        final rows = find.byType(FTile);
        expect(rows, findsWidgets);
        for (var i = 0; i < rows.evaluate().length; i++) {
          expect(
            tester.getSize(rows.at(i)).height,
            greaterThanOrEqualTo(LnSize.minTouch),
          );
        }
      }

      await expectRows();
      await scrollTo(tester, find.textContaining('backtest.py'));
      await expectRows();
    });

    testWidgets('Stop is its own button with the tap action', (tester) async {
      final (api, _) = await pumpRunning(
        tester,
        routes: (api) => api.on(
          'POST /runs/r-1/cancel',
          (_) => {...activeRuns().first.raw, 'status': 'cancelled'},
        ),
      );
      final semantics = tester.ensureSemantics();
      final stop = find.semantics.byLabel(RegExp('^Stop .*متداول الذهب'));
      expect(stop, findsOne);
      expect(
        stop.evaluate().single.getSemanticsData(),
        isSemantics(isButton: true, isEnabled: true, hasTapAction: true),
      );
      // Stop is offered once: no row carries it again as a custom action.
      final custom = find.semantics.byAction(SemanticsAction.customAction);
      expect(custom, findsNothing);
      tester.semantics.tap(stop);
      await tester.pumpAndSettle();
      expect(api.callsTo('POST', '/runs/r-1/cancel'), hasLength(1));
      expect(api.callsTo('POST', '/runs'), isEmpty);
      semantics.dispose();
      await flushToasts(tester);
    });

    testWidgets('a process stops with its pid and agent', (tester) async {
      final (api, _) = await pumpRunning(tester);
      await scrollTo(tester, find.textContaining('backtest.py'));
      // Two runs come first; then this process (the next one is already stopping).
      final stop = find.text('Stop').at(2);
      await tapAndSettle(tester, stop);
      expect(api.callsTo('POST', '/workspace/running/stop').single.body, {
        'pid': 4121,
        'agent_id': 'a-gold',
      });
      await flushToasts(tester);
    });

    testWidgets('a run stops with the conversation Stop endpoint', (
      tester,
    ) async {
      final (api, _) = await pumpRunning(
        tester,
        routes: (api) => api.on(
          'POST /runs/r-1/cancel',
          (_) => {...activeRuns().first.raw, 'status': 'cancelled'},
        ),
      );
      final goldRun = find.byWidgetPredicate(
        (w) =>
            w is PillButton &&
            (w.semanticLabel ?? '').contains('متداول الذهب') &&
            !(w.semanticLabel ?? '').contains('python'),
      );
      expect(goldRun, findsOneWidget);
      await tapAndSettle(tester, find.text('Stop').first);
      expect(api.callsTo('POST', '/runs/r-1/cancel'), hasLength(1));
      // Never a run creation.
      expect(api.callsTo('POST', '/runs'), isEmpty);
      // The stopped run leaves the list; the other one stays.
      expect(goldRun, findsNothing);
      expect(find.textContaining('Waiting for your reply'), findsOneWidget);
      expect(find.text('Stop'), findsWidgets);
    });

    testWidgets('stop all asks first', (tester) async {
      final (api, _) = await pumpRunning(tester);
      await scrollTo(tester, find.text('Stop all'));
      await tapAndSettle(tester, find.text('Stop all'));
      expect(find.text('Stop every process?'), findsOneWidget);
      await tapAndSettle(tester, find.text('Stop all').last);
      expect(api.callsTo('POST', '/workspace/running/stop-all'), hasLength(1));
      await flushToasts(tester);
    });

    testWidgets('a stale list takes no stop', (tester) async {
      await pumpRunning(tester, running: {...runningJson, 'stale': true});
      await scrollTo(tester, find.textContaining('may be out of date'));
      expect(find.textContaining('may be out of date'), findsOneWidget);
      await scrollTo(tester, find.text('Stop all'));
      final processStops = tester
          .widgetList<PillButton>(find.byType(PillButton))
          .where((b) => (b.semanticLabel ?? '').contains(' '))
          .where(
            (b) =>
                (b.semanticLabel ?? '').contains('python') ||
                (b.semanticLabel ?? '').contains('node'),
          );
      expect(processStops, hasLength(2));
      expect(processStops.every((b) => b.onTap == null), isTrue);
      expect(blockButton(tester, 'Stop all').onPressed, isNull);
    });

    testWidgets('the list is read every 4 s only while the page is on top', (
      tester,
    ) async {
      final (api, _) = await pumpRunning(tester);
      int reads() => api.callsTo('GET', '/workspace/running').length;
      final first = reads();
      await tester.pump(RunningScreen.refreshEvery);
      await tester.pump();
      expect(reads(), first + 1);
      // A run opens its conversation over the page: the polling pauses.
      await tapAndSettle(tester, find.textContaining('Waiting for your reply'));
      expect(find.text('stub:/chats/thread/t-lonora'), findsOneWidget);
      final covered = reads();
      await tester.pump(RunningScreen.refreshEvery * 3);
      await tester.pump();
      expect(reads(), covered);
      // Back on the page: read at once, then every 4 s again.
      Navigator.of(tester.element(find.byType(StubPage))).pop();
      await tester.pumpAndSettle();
      expect(reads(), covered + 1);
      await tester.pump(RunningScreen.refreshEvery);
      await tester.pump();
      expect(reads(), covered + 2);
    });

    testWidgets('a failed pull keeps the list and says so', (tester) async {
      var fail = false;
      await pumpRunning(
        tester,
        routes: (api) => api.on('GET /workspace/running', (_) {
          if (fail) throw ApiError.network();
          return runningJson;
        }),
      );
      fail = true;
      await pullToRefresh(tester);
      expect(find.textContaining('Could not connect'), findsOneWidget);
      await scrollTo(tester, find.textContaining('backtest.py'));
      expect(find.textContaining('backtest.py'), findsOneWidget);
      await flushToasts(tester);
    });

    testWidgets('a run started elsewhere appears live', (tester) async {
      final (_, store) = await pumpRunning(tester, runs: const []);
      expect(find.text('No agent is working right now.'), findsOneWidget);
      store.dispatch(
        ApplyEventAction(
          LonoraEvent(
            cursor: 9,
            kind: 'run.queued',
            threadId: 't-research',
            runId: 'r-new',
            payload: {
              'run': {
                'id': 'r-new',
                'thread_id': 't-research',
                'agent_id': 'a-research',
                'status': 'queued',
                'created_at': '2026-11-27T11:31:00+00:00',
              },
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('No agent is working right now.'), findsNothing);
      expect(find.textContaining('Queued'), findsOneWidget);
      // The debounced refetch of the latest runs is not due yet.
      await tester.pump(const Duration(seconds: 1));
    });

    testWidgets('nothing running reads as such', (tester) async {
      await pumpRunning(
        tester,
        runs: const [],
        running: {
          'listed_at': '2026-11-27T11:29:50+00:00',
          'stale': false,
          'stopping_all': false,
          'processes': <Json>[],
        },
      );
      expect(find.text('No agent is working right now.'), findsOneWidget);
      expect(find.text('Nothing is running in the workspace.'), findsOneWidget);
    });

    for (final v in goldenVariants) {
      testWidgets('golden ${v.name}', (tester) async {
        await withRealShadows(() async {
          await pumpRunning(tester, locale: v.locale, theme: v.theme);
          await expectLater(
            find.byType(WidgetsApp),
            matchesGoldenFile('goldens/running_${v.name}.png'),
          );
        });
      });
    }
  });
}
