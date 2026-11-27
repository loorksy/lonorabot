// The WP-A2 data layer against a REAL Lonora server (no API mocks): providers, routing, model
// lists, capabilities, trading connections, usage (series, rank, summary, CSV), what is running
// and the owner's runs. Writes are only reversible ones, undone in the same test: the routing
// is saved back unchanged, an RSS feed is added then deleted, a removed trusted source is
// restored then removed again, and a simulation connection (no credential at all) is linked
// then unlinked. Adding the feed trusts its domain and deleting it revokes that trust, so each
// run leaves one more revoked `a2-check.example.org` source (no route deletes a trusted
// source; it carries no access). Nothing trades, no run is created, no provider key is tested
// (that would reach a provider).
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
import 'package:lonora/features/settings/integrations/integrations_data.dart';
import 'package:lonora/features/settings/models/models_data.dart';
import 'package:lonora/features/settings/running/running_data.dart';
import 'package:lonora/features/settings/usage/usage_data.dart';
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
    final dir = await Directory.systemTemp.createTemp('lonora_a2');
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
    await store.dispatchAndWait(SignOutAction());
    realtime.stop();
  });

  final skip = creds == null ? 'LONORA_TEST_CREDS is not set' : false;

  test('providers and model lists: status only, never a key', () async {
    final providers = await fetchProviders();
    expect(providers.map((p) => p.id), containsAll(['openai', 'anthropic']));
    final raw = jsonEncode(await api.get('/providers'));
    expect(raw, isNot(contains('api_key')));
    final models = await fetchModels('openai');
    expect(models, isNotEmpty);
    expect(models.every((m) => m.provider == 'openai'), isTrue);
    // Connected lists only (none on a fresh server is fine).
    final connected = await fetchConnectedModels(providers);
    expect(
      connected.every(
        (m) => providers.any((p) => p.id == m.provider && p.configured),
      ),
      isTrue,
    );
  }, skip: skip);

  test('global routing reads and saves back unchanged', () async {
    final before = await fetchRouting();
    final saved = await saveRouting(before);
    expect(saved, before);
    expect(await fetchRouting(), before);
  }, skip: skip);

  test(
    'capabilities, secrets by name, an RSS feed added and removed',
    () async {
      final report = await fetchCapabilities();
      expect(report.builtIn, isNotEmpty);
      expect(asStr(report.raw['authority']), contains('no capability'));
      final secrets = await fetchSecrets();
      for (final s in secrets) {
        expect(s.keys, isNot(contains('value')));
      }
      const url = 'https://a2-check.example.org/feed.xml';
      await addFeed(url);
      final added = (await fetchCapabilities()).feeds
          .where(
            (f) =>
                f['domain'] == 'a2-check.example.org' ||
                f['name'] == 'a2-check.example.org',
          )
          .toList();
      expect(added, hasLength(1));
      await removeIntegration(asStr(added.single['id']));
      expect(
        (await fetchCapabilities()).feeds.where(
          (f) => f['id'] == added.single['id'],
        ),
        isEmpty,
      );
    },
    skip: skip,
  );

  test('a removed trusted source is restored, then removed again', () async {
    final removed = (await fetchCapabilities()).trustedSources
        .where((s) => !asBool(s['active']) && s['kind'] == 'feed_domain')
        .toList();
    // The feed test above leaves one behind.
    expect(removed, isNotEmpty);
    final id = asStr(removed.first['id']);
    Future<bool> active() async => asBool(
      (await fetchCapabilities()).trustedSources.firstWhere(
        (s) => s['id'] == id,
      )['active'],
    );
    await setSourceActive(id, active: true);
    try {
      expect(await active(), isTrue);
    } finally {
      await setSourceActive(id, active: false);
    }
    expect(await active(), isFalse);
  }, skip: skip);

  test('a simulation account is checked, linked and unlinked', () async {
    final before = await fetchConnections();
    final id = 'a2-sim-${DateTime.now().millisecondsSinceEpoch}';
    final body = brokerBody('simulation', {'account_id': id});
    final check = await testBroker(body);
    expect(check['provider'], 'simulation');
    final row = await linkBroker(body);
    try {
      expect(row.isSimulation, isTrue);
      expect(row.number, id);
      expect((await fetchConnections()).map((c) => c.id), contains(row.id));
      // No snapshot yet: the account says so instead of inventing a balance.
      await expectLater(
        fetchAccount(row.id),
        throwsA(
          isA<ApiError>().having(
            (e) => e.code,
            'code',
            'simulation_snapshot_required',
          ),
        ),
      );
    } finally {
      await unlinkBroker(row.id);
    }
    expect(
      (await fetchConnections()).map((c) => c.id),
      before.map((c) => c.id),
    );
  }, skip: skip);

  test('usage: series, rank, summary and the CSV export', () async {
    // No zone is sent (as on the Web): the server answers in the owner's stored zone.
    final month = await fetchSeries(UsagePeriod.month);
    expect(month.points, hasLength(30));
    expect(month.timezone, isNotEmpty);
    final day = await fetchSeries(UsagePeriod.day);
    expect(day.hourly, isTrue);
    expect(day.points, hasLength(24));
    final week = await fetchSeries(UsagePeriod.week);
    expect(week.points, hasLength(7));
    final rank = await fetchRank(UsagePeriod.month);
    expect(rank.totals.requests, greaterThanOrEqualTo(0));
    final agentId = rank.agents.where((a) => a.agentId != null).firstOrNull;
    if (agentId != null) {
      final mine = await fetchSeries(
        UsagePeriod.month,
        agentId: agentId.agentId,
      );
      expect(mine.totals.requests, lessThanOrEqualTo(month.totals.requests));
    }
    final summary = await fetchUsageSummary();
    expect(summary.input, greaterThanOrEqualTo(0));
    final file = File(
      '${(await Directory.systemTemp.createTemp('a2csv')).path}/u.csv',
    );
    await downloadUsageCsv(file.path, UsagePeriod.week);
    final bytes = await file.readAsBytes();
    expect(bytes.take(3), [0xEF, 0xBB, 0xBF]); // UTF-8 BOM
  }, skip: skip);

  test('what is running and the owner runs', () async {
    final view = await fetchWorkspaceRunning();
    expect(view.processes.every((p) => p.pid > 0), isTrue);
    await store.dispatchAndWait(RefreshOwnerRunsAction());
    final runs = runsInProgress(store.state.shell.runs);
    expect(runs.every((r) => !r.isTerminal), isTrue);
  }, skip: skip);
}
