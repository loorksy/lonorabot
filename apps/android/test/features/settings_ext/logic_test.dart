// The non-trivial rules of the WP-A2 pages: cost formatting and chart scale (as the Web prints
// them), the owner-zone wall clock, routing edits and model filters, broker bodies and
// identities, domain and feed checks, MCP tool counts, runs in progress.
import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/settings/integrations/integrations_data.dart';
import 'package:lonora/features/settings/models/models_data.dart';
import 'package:lonora/features/settings/running/running_data.dart';
import 'package:lonora/features/settings/usage/usage_data.dart';
import 'package:lonora/features/settings/usage/usage_widgets.dart'
    show usageCount;

import 'ext_harness.dart';
import 'fixtures.dart';

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    await setUpExtTests();
  });

  group('usd (apps/web UsagePage.tsx)', () {
    test('cents, whole dollars and grouping', () {
      expect(usd(0), r'$0.00');
      expect(usd(null), r'$0.00');
      expect(usd(12.468), r'$12.47');
      expect(usd(0.1), r'$0.10');
      expect(usd(150.4), r'$150');
      expect(usd(12345.6), r'$12,346');
    });

    test('a tiny cost never reads as zero', () {
      expect(usd(0.0123), r'$0.012');
      expect(usd(0.004), r'$0.0040');
      expect(usd(0.00001), r'$0.0001');
    });
  });

  group('chart scale', () {
    test('a nice top above the largest bucket', () {
      expect(chartTop([0.95, 0.5]), closeTo(1.2, 1e-9));
      expect(chartTop([0, 0]), 2);
      expect(niceCeiling(0.37), closeTo(0.4, 1e-9));
      expect(niceCeiling(7), 8);
    });

    test('axis ticks keep the decimals they need', () {
      expect(axisTick(0), r'$0');
      expect(axisTick(1.2), r'$1.20');
      expect(axisTick(0.6), r'$0.60');
      expect(axisTick(2), r'$2');
      expect(axisTick(0.025), r'$0.025');
    });

    test('change against the previous window', () {
      expect(percentChange(12.47, 9.82), 27);
      expect(percentChange(5, 10), -50);
      expect(percentChange(5, 0), isNull);
    });
  });

  group('series', () {
    test('buckets keep the owner zone wall clock', () {
      expect(
        wallClock('2026-11-27T00:00:00+03:00'),
        DateTime.utc(2026, 11, 27),
      );
      expect(
        wallClock('2026-11-21T13:00:00-05:00'),
        DateTime.utc(2026, 11, 21, 13),
      );
      expect(wallClock('nonsense'), isNull);
    });

    test('future hours are not started and the reading starts at now', () {
      final series = UsageSeries.fromJson(seriesJson(period: 'day'));
      expect(series.hourly, isTrue);
      expect(series.points, hasLength(24));
      expect(series.points[20].figures.future, isTrue);
      expect(series.lastStarted, 14);
      expect(series.month.end, DateTime.utc(2026, 11, 30));
    });

    test('a model without a list price has no cost', () {
      final rank = UsageRank.fromJson(rankJson);
      expect(rank.models.last.figures.costUsd, isNull);
      expect(rank.models.last.figures.cost, 0);
      expect(rank.agents.last.agentId, isNull);
    });

    test('counts as the Web prints them, in both languages', () {
      expect(usageCount(1320), '1,320');
      expect(usageCount(9999), '9,999');
      expect(usageCount(12345), '12.3K');
      expect(usageCount(99999), '100K');
      expect(usageCount(123456), '123K');
      expect(usageCount(999999), '1M');
      expect(usageCount(1234567), '1.23M');
      expect(usageCount(18400000), '18.4M');
      expect(usageCount(2500000000), '2.5B');
    });
  });

  group('routing', () {
    final policy = RoutingPolicy.fromJson(routingJson);

    test('one model for text work keeps only the voice routes', () {
      final custom = policy
          .withMode('custom')
          .withRoute('vision', const ModelSelection('openai', 'gpt-5'));
      expect(custom.routes.keys, containsAll(['vision', 'realtime_voice']));
      final unified = custom.withMode('unified');
      expect(unified.routes.keys, ['realtime_voice']);
      expect(unified.toJson()['unified'], {
        'provider': 'openai',
        'model': 'gpt-5',
      });
    });

    test('a cleared route is dropped; equality follows the routes', () {
      final cleared = policy.withRoute('realtime_voice', null);
      expect(cleared.routes, isEmpty);
      expect(cleared == policy, isFalse);
      expect(
        policy.withRoute(
              'realtime_voice',
              const ModelSelection('openai', 'gpt-live-1'),
            ) ==
            policy,
        isTrue,
      );
    });

    test('each route offers the models that can do its work', () {
      final models = [
        ...openAiModels,
        ...anthropicModels,
      ].map(ModelDescriptor.fromJson).toList();
      final vision = modelsFor('vision', models, speech: true);
      expect(vision.map((m) => m.id), isNot(contains('gpt-4')));
      // Unverified capabilities are always offered.
      expect(vision.map((m) => m.id), contains('claude-experimental'));
      expect(modelsFor('conversation', models, speech: true), hasLength(5));
      expect(
        modelsFor('realtime_voice', models, speech: true).map((m) => m.id),
        ['gpt-live-1', 'gpt-live-1-mini'],
      );
      expect(modelsFor('tts', models, speech: false), isEmpty);
    });

    test('a selection reads by its listed name', () {
      final models = openAiModels.map(ModelDescriptor.fromJson).toList();
      expect(
        selectionLabel(const ModelSelection('openai', 'gpt-5'), models),
        'OpenAI · GPT-5',
      );
      expect(
        selectionLabel(const ModelSelection('zai', 'glm-5'), models),
        'Z.ai · glm-5',
      );
    });
  });

  group('integrations', () {
    test('broker bodies carry every field, empty ones as null', () {
      expect(
        brokerBody('metaapi', {'account_id': ' 7310 ', 'api_key': 'x' * 10}),
        {
          'provider': 'metaapi',
          'enabled': true,
          'account_id': '7310',
          'api_key': 'x' * 10,
          'region': null,
        },
      );
      expect(brokerBody('simulation', {'account_id': 'p1', 'api_key': 'k'}), {
        'provider': 'simulation',
        'enabled': true,
        'account_id': 'p1',
      });
    });

    test('a broker identity counts only for its connection version', () {
      final row = BrokerConnection.fromJson(connectionsJson.first);
      expect(row.identity?.login, '7310455');
      expect(row.number, '7310455');
      final stale = BrokerConnection.fromJson({
        ...connectionsJson.first,
        'version': 2,
      });
      expect(stale.identity, isNull);
      // A MetaApi provisioning id is never shown as an account number.
      expect(stale.number, isNull);
      final sim = BrokerConnection.fromJson(connectionsJson.last);
      expect(sim.isSimulation, isTrue);
      expect(sim.number, 'paper-01');
    });

    test('domains and feed links as the Web accepts them', () {
      expect(
        normalizeDomain('https://WWW.Reuters.com/markets'),
        'www.reuters.com',
      );
      expect(normalizeDomain('ft.com'), 'ft.com');
      expect(normalizeDomain('not a domain'), isNull);
      expect(normalizeDomain('localhost'), isNull);
      expect(isFeedUrl('https://feeds.reuters.com/x.xml'), isTrue);
      expect(isFeedUrl('ftp://feeds.example.com'), isFalse);
    });

    test('MCP tools by level in each language', () {
      final server = {
        'trusted_tools': ['a', 'b', 'c', 'd'],
        'write_tools': ['d'],
      };
      testL10n.setLocale(const Locale('en'));
      expect(
        mcpLevelText(testL10n, server),
        '3 read tools\u00a0· one non-financial write tool',
      );
      expect(
        mcpLevelText(testL10n, {
          'trusted_tools': [for (var i = 0; i < 13; i++) 't$i'],
          'write_tools': ['t0', 't1'],
        }),
        '11 read tools\u00a0· two non-financial write tools',
      );
      expect(mcpLevelText(testL10n, {'trusted_tools': []}), '');
      testL10n.setLocale(const Locale('ar'));
      expect(
        mcpLevelText(testL10n, server),
        '3 أدوات قراءة\u00a0· أداة كتابة غير مالية واحدة',
      );
      expect(
        mcpLevelText(testL10n, {
          'trusted_tools': [for (var i = 0; i < 13; i++) 't$i'],
          'write_tools': ['t0', 't1'],
        }),
        '11 أداة قراءة\u00a0· أداتا كتابة غير مالية',
      );
    });

    test('the capability report finds feeds, Telegram and the rest', () {
      final report = CapabilityReport(capabilitiesJson);
      expect(report.feedDomains.map((s) => s['identifier']), [
        'reuters.com',
        'ft.com',
      ]);
      expect(report.githubSources, hasLength(1));
      expect(report.telegram?['id'], 'i-telegram');
      expect(report.otherIntegrations.single['id'], 'i-calendar');
      expect(report.sourceOf(report.mcpServers.first)?['id'], 's-mcp');
    });
  });

  group('running', () {
    test('runs in progress: unfinished, parents only, newest first', () {
      final runs = runsInProgress(activeRuns());
      expect(runs.map((r) => r.id), ['r-1', 'r-2']);
    });

    test('a child whose parent finished is listed on its own', () {
      final runs = runsInProgress([
        Run.fromJson({
          'id': 'child',
          'thread_id': 't',
          'agent_id': 'a',
          'parent_run_id': 'done-parent',
          'status': 'running',
        }),
      ]);
      expect(runs.single.id, 'child');
    });

    test('processes group by agent in server order', () {
      final view = WorkspaceRunning.fromJson(runningJson);
      expect(view.byAgent.keys, ['a-gold', 'a-research']);
      expect(view.byAgent['a-gold'], hasLength(2));
      expect(view.processes[1].stopping, isTrue);
      expect(view.processes.first.key, 'a-gold:4121');
    });
  });
}
