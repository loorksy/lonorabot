// Real-backend check of the market, charts, attention and files reads against a REAL disposable
// Lonora server (no API mocks). Writes are reversible and undone in the same test: a simulation
// connection (no credentials) and a chart are created then deleted; a text file is uploaded,
// edited with its version, then deleted. Nothing places, changes or closes an order. Attention
// items are only read (a seen mark cannot be undone).
//
// Runs only when LONORA_TEST_CREDS points at a JSON file {server_url, owner_email,
// owner_password} of a disposable test server. Never point it at production.
import 'dart:convert';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/features/attention/attention_actions.dart';
import 'package:lonora/features/charts/charts_data.dart';
import 'package:lonora/features/files/files_data.dart';
import 'package:lonora/features/market/market_data.dart';
import 'package:lonora/features/market/watch_sheet.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _MemorySecureStore extends SecureStore {
  _MemorySecureStore() : super(const FlutterSecureStorage());
  StoredSession? session;
  @override
  Future<StoredSession?> readSession() async => session;
  @override
  Future<void> writeSession(StoredSession s) async => session = s;
  @override
  Future<void> clearSession() async => session = null;
  @override
  Future<String?> lastServer() async => session?.server;
  @override
  Future<String?> lastEmail() async => session?.email;
  @override
  Future<void> rememberServer(String server) async {}
}

/// A small simulation snapshot: one instrument, its quote and 40 hourly candles.
Json simulationSnapshot() {
  final t0 = DateTime.utc(2026, 11, 25);
  var p = 2380.0;
  final candles = <Json>[];
  for (var i = 0; i < 40; i++) {
    final o = p;
    final c = p + ((i * 7) % 5 - 2) * 0.8;
    candles.add({
      'symbol': 'XAUUSD',
      'timeframe': '1h',
      'time': t0.add(Duration(hours: i)).toIso8601String(),
      'open': o.toStringAsFixed(2),
      'high': ((o > c ? o : c) + 1.5).toStringAsFixed(2),
      'low': ((o < c ? o : c) - 1.2).toStringAsFixed(2),
      'close': c.toStringAsFixed(2),
      'volume': '10',
    });
    p = c;
  }
  return {
    'currency': 'USD',
    'balance': '10000',
    'login': 7001,
    'broker': 'WPF Sim',
    'server': 'Paper-1',
    'instruments': [
      {
        'symbol': 'XAUUSD',
        'description': 'Gold',
        'digits': 2,
        'tick_size': '0.01',
        'volume_min': '0.01',
        'volume_max': '50',
        'volume_step': '0.01',
      },
    ],
    'quotes': {
      'XAUUSD': {
        'symbol': 'XAUUSD',
        'bid': '2401.10',
        'ask': '2401.40',
        'observed_at': DateTime.now().toUtc().toIso8601String(),
        'source': 'simulation',
      },
    },
    'candles': {'XAUUSD:1h': candles},
  };
}

void main() {
  final credsPath = Platform.environment['LONORA_TEST_CREDS'];
  final creds = credsPath != null && File(credsPath).existsSync()
      ? asJson(jsonDecode(File(credsPath).readAsStringSync()))
      : null;
  late Store<AppState> store;

  setUpAll(() async {
    if (creds == null) return;
    TestWidgetsFlutterBinding.ensureInitialized();
    HttpOverrides.global = null; // real network for this test
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('ai.lonora.android/platform'),
          (call) async => null,
        );
    SharedPreferences.setMockInitialValues({});
    final dir = await Directory.systemTemp.createTemp('lonora_wpf');
    cacheDirectory = () async => dir;
    await registerServices(
      apiClient: ApiClient(userAgent: 'Lonora-Android/test'),
      secure: _MemorySecureStore(),
      local: LocalStore.at(dir),
      prefs: await SharedPreferences.getInstance(),
      info: const AppInfo(
        version: '1.0.0',
        buildNumber: '1',
        packageName: 'ai.lonora.android',
      ),
    );
    store = Store<AppState>(initialState: const AppState());
    realtime = RealtimeController(store);
    await store.dispatchAndWait(
      SignInAction(
        server: asStr(creds['server_url']),
        email: asStr(creds['owner_email']),
        password: asStr(creds['owner_password']),
      ),
    );
    expect(store.state.session.signedIn, isTrue);
  });

  tearDownAll(() async {
    if (creds == null) return;
    realtime.stop();
    await api.post('/auth/logout'); // the session this test opened
  });

  test(
    'market reads with a temporary simulation account, chart lifecycle',
    () async {
      // Owner-wide reads.
      final connections = await fetchMarketConnections();
      expect(connections, isA<List<MarketConnection>>());
      expect(await fetchWatches(), isA<List<MarketWatch>>());
      expect(await fetchCalendar(), isA<List<CalendarEvent>>());
      expect(await fetchOpportunities(), isA<List<Opportunity>>());
      expect(await fetchChartRefs(), isA<List<ChartRef>>());

      String? connectionId;
      String? chartId;
      final watchIds = <String>[];
      try {
        final created = asJson(
          await api.post('/trading/connections', {
            'provider': 'simulation',
            'account_id': 'wpf-${DateTime.now().millisecondsSinceEpoch}',
            'enabled': true,
          }),
        );
        connectionId = asStr(created['id']);
        await api.post('/trading/connections/$connectionId/simulation', {
          'snapshot': simulationSnapshot(),
        });

        final mine = (await fetchMarketConnections()).firstWhere(
          (c) => c.id == connectionId,
        );
        expect(mine.isSimulation, isTrue);
        expect(defaultAccount([mine], const []), connectionId);

        final snapshot = await fetchAccountSnapshot(connectionId);
        expect(snapshot.currency, 'USD');
        expect(snapshot.balance, 10000);
        expect(snapshot.equity, 10000);
        expect(snapshot.positions, isEmpty);

        expect(await fetchMarketSymbols(connectionId), ['XAUUSD']);
        final quote = await fetchQuote(connectionId, 'XAUUSD');
        expect(quote.bid, '2401.10');
        expect(quote.spread, '0.30');
        final instrument = await fetchInstrument(connectionId, 'XAUUSD');
        expect(instrument.tickSize, '0.01');
        final candles = await fetchCandles(connectionId, 'XAUUSD', limit: 10);
        expect(candles, hasLength(10));
        expect(candles.last.time.isAfter(candles.first.time), isTrue);
        expect(await fetchJournal(connectionId), isEmpty);

        // A price watch far from the market (it never triggers), with an expiry: pause,
        // resume, cancel, undo the cancel (resume), extend, cancel.
        final agents = asJsonList(await api.get('/agents'));
        final agentId = asStr(
          agents.firstWhere((a) => a['paused'] != true)['id'],
        );
        final watch = await createWatch(
          agentId: agentId,
          payload: {
            ...watchPayload(
              kind: 'price',
              accountId: connectionId,
              symbol: 'XAUUSD',
              condition: 'above',
              level: '999999',
              prompt: 'WPF reversible test watch',
            ),
            'expires_at': DateTime.now()
                .toUtc()
                .add(const Duration(hours: 1))
                .toIso8601String(),
          },
        );
        watchIds.add(watch.id);
        expect(watch.symbol, 'XAUUSD');
        expect(watch.paused, isFalse);
        expect(watch.extendable, isTrue);
        expect((await fetchWatches()).map((w) => w.id), contains(watch.id));
        expect((await controlWatch(watch.id, 'pause')).paused, isTrue);
        expect((await controlWatch(watch.id, 'resume')).paused, isFalse);
        final cancelled = await controlWatch(watch.id, 'cancel');
        expect(cancelled.cancelled, isTrue);
        expect(cancelled.ended, isTrue);
        final undone = await controlWatch(watch.id, 'resume');
        expect((undone.cancelled, undone.paused), (false, false));
        final extended = await controlWatch(watch.id, 'extend', hours: 2);
        expect(extended.expiresAt!.difference(watch.expiresAt!).inMinutes, 120);
        expect((await controlWatch(watch.id, 'cancel')).ended, isTrue);
        // The watch works in a hidden thread of its agent: its files read by conversation.
        expect(await fetchArtifacts(threadId: watch.threadId), isA<List>());

        // The other sources the sheet offers are taken by the Watch contract.
        final indicator = await createWatch(
          agentId: agentId,
          payload: watchPayload(
            kind: 'indicator',
            accountId: connectionId,
            symbol: 'XAUUSD',
            condition: 'below',
            level: '5',
            indicator: 'rsi',
            period: 21,
            timeframe: '4h',
            prompt: 'WPF reversible indicator watch',
          ),
        );
        watchIds.add(indicator.id);
        expect(indicator.summary['indicator'], 'rsi');
        expect(indicator.summary['timeframe'], '4h');
        final account = await createWatch(
          agentId: agentId,
          payload: watchPayload(
            kind: 'account',
            accountId: connectionId,
            symbol: 'XAUUSD',
            condition: 'changed',
            metric: 'free_margin',
            prompt: 'WPF reversible account watch',
          ),
        );
        watchIds.add(account.id);
        expect(account.summary['metric'], 'free_margin');
        // A calendar watch needs a feed; this server has none.
        expect(await fetchCalendarFeeds(), isEmpty);
        await expectLater(
          createWatch(
            agentId: agentId,
            payload: watchPayload(
              kind: 'calendar',
              accountId: connectionId,
              symbol: 'XAUUSD',
              condition: 'due',
              prompt: 'never created',
            ),
          ),
          throwsA(isA<ApiError>()),
        );

        // Chart: create, wait for its first scene, ask for a refresh.
        final chart = await createChart(
          accountId: connectionId,
          symbol: 'XAUUSD',
          timeframe: '1h',
        );
        chartId = chart.id;
        expect(chart.symbol, 'XAUUSD');
        ChartScene? scene;
        for (var i = 0; i < 40 && scene == null; i++) {
          try {
            scene = await fetchScene(chartId);
          } on ApiError catch (e) {
            expect(e.code, 'chart_initializing');
            await Future<void>.delayed(const Duration(milliseconds: 500));
          }
        }
        expect(scene, isNotNull, reason: 'the scene was never ready');
        expect(scene!.symbol, 'XAUUSD');
        expect(scene.candles, isNotEmpty);
        await requestChartRefresh(chartId);
        expect((await fetchCharts()).map((r) => r.id), contains(chartId));
      } finally {
        for (final id in watchIds) {
          await api.delete('/watches/$id');
        }
        if (chartId != null) await api.delete('/charts/$chartId');
        if (connectionId != null) {
          await api.delete('/trading/connections/$connectionId');
        }
      }
      expect(
        (await fetchMarketConnections()).map((c) => c.id),
        isNot(contains(connectionId)),
      );
      expect((await fetchCharts()).map((r) => r.id), isNot(contains(chartId)));
      expect(
        (await fetchWatches()).map((w) => w.id).toSet().intersection({
          ...watchIds,
        }),
        isEmpty,
      );
    },
    skip: creds == null ? 'LONORA_TEST_CREDS not set' : false,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test('attention view rows and items are read into the shell', () async {
    final load = LoadAttentionAction();
    await store.dispatchAndWait(load);
    expect(load.error, isNull);
    final rows = store.state.shell.attentionView;
    for (final r in rows) {
      expect(r['id'], isA<String>());
      expect(r['kind'], isA<String>());
      expect(r['thread_id'], isA<String>());
      expect(r['seen'], isA<bool>());
    }
    expect(
      store.state.shell.attentionUnseen,
      rows.where((r) => r['seen'] != true).length,
    );
  }, skip: creds == null ? 'LONORA_TEST_CREDS not set' : false);

  test(
    'files: list, read, upload, edit with its version, delete',
    () async {
      final before = await fetchArtifacts();
      ArtifactRecord? created;
      try {
        created = await createTextArtifact(
          name: 'wpf-note.md',
          content: '# WPF\n\nA reversible test file.',
        );
        expect(created.kind, FileKind.markdown);
        final read = await fetchArtifact(created.id);
        expect(read.name, 'wpf-note.md');
        final bytes = await fetchArtifactBytes(read);
        expect(utf8.decode(bytes), contains('reversible'));

        final edited = await saveArtifactText(
          read,
          name: 'wpf-note.md',
          content: '# WPF\n\nEdited.',
        );
        expect(edited.version, greaterThan(read.version));
        // The old version is refused.
        await expectLater(
          saveArtifactText(read, name: 'wpf-note.md', content: 'stale'),
          throwsA(
            isA<ApiError>().having((e) => e.code, 'code', 'version_conflict'),
          ),
        );
        expect((await fetchArtifacts()).map((r) => r.id), contains(created.id));
      } finally {
        if (created != null) await deleteArtifact(created.id);
      }
      expect(
        (await fetchArtifacts()).map((r) => r.id).toSet(),
        before.map((r) => r.id).toSet(),
      );
      if (before.isNotEmpty) {
        final first = before.first;
        if (first.size < 2 * 1024 * 1024) {
          final data = await fetchArtifactBytes(first);
          expect(data.length, first.size);
        }
      }
    },
    skip: creds == null ? 'LONORA_TEST_CREDS not set' : false,
    timeout: const Timeout(Duration(minutes: 1)),
  );
}
