// Work package E against a REAL Lonora server (no mocks of the API): every read endpoint of the
// agent profile, settings, memory, skills, routines, tasks and «ما أعرفه عنك» pages parsed by
// the screens' own data layer, and the reversible writes, each restored in the same test
// (delivery rules, the agent's title, a disabled routine, a knowledge note and link, an owner
// skill). Nothing here pauses an agent, decides a card, creates a task or touches trading.
//
// Runs only when LONORA_TEST_CREDS points at a JSON file {server_url, owner_email,
// owner_password} of a disposable test server (docs/android/analysis/lonora-local-runtime.md).
// Never point it at production.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/features/agents/profile/agent_data.dart';
import 'package:lonora/features/routines/routines_data.dart';
import 'package:lonora/features/skills/skills_data.dart';
import 'package:lonora/features/tasks/tasks_data.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _NoSecureStore extends SecureStore {
  _NoSecureStore() : super(const FlutterSecureStorage());
  @override
  Future<StoredSession?> readSession() async => null;
  @override
  Future<void> writeSession(StoredSession s) async {}
  @override
  Future<void> clearSession() async {}
  @override
  Future<String?> lastServer() async => null;
  @override
  Future<String?> lastEmail() async => null;
  @override
  Future<void> rememberServer(String server) async {}
}

void main() {
  final credsPath = Platform.environment['LONORA_TEST_CREDS'];
  final creds = credsPath != null && File(credsPath).existsSync()
      ? asJson(jsonDecode(File(credsPath).readAsStringSync()))
      : null;
  final skip = creds == null ? 'LONORA_TEST_CREDS is not set' : null;

  late Agent agent;

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
    final dir = await Directory.systemTemp.createTemp('lonora_wpe');
    final client = ApiClient(userAgent: 'Lonora-Android/test');
    await registerServices(
      apiClient: client,
      secure: _NoSecureStore(),
      local: LocalStore.at(dir),
      prefs: await SharedPreferences.getInstance(),
      info: const AppInfo(
        version: '1.0.0',
        buildNumber: '1',
        packageName: 'ai.lonora.android',
      ),
    );
    final server = asStr(creds['server_url']);
    client.configure(server: server);
    final login = asJson(
      await client.post('/auth/mobile/login', {
        'email': asStr(creds['owner_email']),
        'password': asStr(creds['owner_password']),
      }),
    );
    client.configure(server: server, token: asStr(login['token']));
    final agents = asJsonList(await api.get('/agents')).map(Agent.fromJson);
    // A team agent when there is one (writes stay off the personal agent).
    agent = agents.firstWhere((a) => !a.isPersonal, orElse: () => agents.first);
  });

  tearDownAll(() async {
    if (creds == null) return;
    await api.post('/auth/logout'); // the session this test opened
  });

  test('agent hub reads', () async {
    final fresh = await fetchAgent(agent.id);
    expect(fresh.id, agent.id);
    final live = await fetchAgentState(agent.id);
    expect(live['agent_id'], agent.id);
    expect(live, contains('trading_readiness'));
    expect(await fetchWatches(agent.id), isA<List<Watch>>());
    // Reading the Mandate never raises a card.
    final card = await fetchMandate(agent.id);
    expect(card == null || card['kind'] == 'trading_mode', isTrue);
    final summary = await fetchModelSummary(agent.id);
    expect(asJson(summary['record'])['revision'], isA<int>());
    expect(asJson(summary['usage'])['days'], isA<int>());
  }, skip: skip);

  test('delivery rules: save, read back, restore', () async {
    final before = await fetchDeliveryRules(agent.id);
    try {
      final changed = await saveDeliveryRules(
        agent.id,
        before.copyWith(calls: !before.calls, dailyLimit: 7),
      );
      expect(changed.calls, !before.calls);
      expect(changed.dailyLimit, 7);
      expect(await fetchDeliveryRules(agent.id), changed);
    } finally {
      await saveDeliveryRules(agent.id, before);
    }
    expect(await fetchDeliveryRules(agent.id), before);
  }, skip: skip);

  test('identity: a title change is restored', () async {
    final before = await fetchAgent(agent.id);
    try {
      final changed = await patchAgent(agent.id, {
        'title': 'Android check ${DateTime.now().millisecondsSinceEpoch}',
      });
      expect(changed.title, startsWith('Android check'));
      expect(changed.paused, before.paused);
    } finally {
      await patchAgent(agent.id, {'title': before.title});
    }
    expect((await fetchAgent(agent.id)).title, before.title);
  }, skip: skip);

  test('memory and owner knowledge reads', () async {
    final memory = await fetchMemory(agent.id);
    expect(memory.version, greaterThanOrEqualTo(1));
    expect(await fetchMemoryRevisions(agent.id), isA<List<MemoryRevision>>());
    expect(await fetchProfileRevisions(), isA<List<MemoryRevision>>());
    final lines = asJson(await api.get('/owner/profile/lines'));
    expect(lines['version'], isA<int>());
    expect(lines['lines'], isA<List<Object?>>());
    final habit = asJson(await api.get('/app-opens'));
    expect(habit, contains('brief'));
    final profile = asJson(await api.get('/owner/profile'));
    expect(profile['version'], isA<int>());
  }, skip: skip);

  test('knowledge: a note and a link are added, edited and deleted', () async {
    final stamp = DateTime.now().millisecondsSinceEpoch;
    await addKnowledgeNote(agent.id, 'Android note $stamp', 'First line.');
    var items = await fetchKnowledge(agent.id);
    final note = items.firstWhere((i) => i.title == 'Android note $stamp');
    expect(note.isLink, isFalse);
    try {
      await saveKnowledgeNote(
        agent.id,
        note.id,
        'Android note $stamp',
        'Edited line.',
      );
      await addKnowledgeLink(agent.id, {
        'title': 'Android link $stamp',
        'url': 'https://example.com/$stamp',
        'note': 'A link.',
      });
      items = await fetchKnowledge(agent.id);
      final link = items.firstWhere((i) => i.title == 'Android link $stamp');
      expect(link.isLink, isTrue);
      expect(link.url, 'https://example.com/$stamp');
      await deleteKnowledgeLink(link.id);
    } finally {
      for (final i in await fetchKnowledge(agent.id)) {
        if (!i.isLink && i.title == 'Android note $stamp') {
          await deleteKnowledgeNote(agent.id, i.id);
        }
      }
    }
    final left = await fetchKnowledge(agent.id);
    expect(left.where((i) => i.title.endsWith('$stamp')), isEmpty);
  }, skip: skip);

  test(
    'goals and scratchpad: created, edited with their version, removed',
    () async {
      final stamp = DateTime.now().millisecondsSinceEpoch;
      for (final (kind, payload, edited) in [
        (
          goalsKind,
          {'title': 'Android goal $stamp', 'description': '', 'done': false},
          {'title': 'Android goal $stamp', 'description': 'd', 'done': true},
        ),
        (
          scratchpadKind,
          {'title': 'Android pad $stamp', 'content': 'x'},
          {'title': 'Android pad $stamp', 'content': 'y'},
        ),
      ]) {
        await createAgentResource(kind, agent.id, payload);
        try {
          final row = (await fetchAgentResources(
            kind,
            agent.id,
          )).firstWhere((r) => r.text('title') == payload['title']);
          await saveAgentResource(kind, row, edited);
          final saved = (await fetchAgentResources(
            kind,
            agent.id,
          )).firstWhere((r) => r.id == row.id);
          expect(saved.payload, edited);
          expect(saved.version, row.version + 1);
          // The row's old version is refused, never applied.
          await expectLater(
            saveAgentResource(kind, row, payload),
            throwsA(
              isA<ApiError>().having((e) => e.code, 'code', 'version_conflict'),
            ),
          );
        } finally {
          for (final r in await fetchAgentResources(kind, agent.id)) {
            if (r.text('title') == payload['title']) {
              await deleteAgentResource(kind, r.id);
            }
          }
        }
        final left = await fetchAgentResources(kind, agent.id);
        expect(left.where((r) => r.text('title') == payload['title']), isEmpty);
      }
      // The semantic setting is the owner's, read only here.
      final semantic = await fetchSemanticConfig();
      expect(semantic, isA<SemanticConfig>());
    },
    skip: skip,
  );

  test('routines: a disabled routine is created, edited and deleted', () async {
    final draft = RoutineSchedule.initial(DateTime.now())
        .copyWith(repeat: RepeatKind.weekdays, hour: 6, minute: 15);
    // Created switched off: nothing runs.
    final created = await createRoutine(agent.id, {
      ...routineTitleInput(null, 'Android routine check'),
      'prompt': 'Android routine check',
      ...draft.toInput(),
      'timezone': 'Asia/Riyadh',
      'enabled': false,
    });
    try {
      expect(created.cron, '15 6 * * 1-5');
      expect(created.enabled, isFalse);
      expect(
        RoutineSchedule.of(created, DateTime.now()).repeat,
        RepeatKind.weekdays,
      );
      final listed = await fetchRoutines(agentId: agent.id);
      expect(listed.map((r) => r.id), contains(created.id));
      final edited = await updateRoutine(created.id, {'cron': '0 7 15 * *'});
      expect(edited.cron, '0 7 15 * *');
      expect(edited.prompt, 'Android routine check');
      expect(edited.enabled, isFalse);
      expect(await fetchRoutineHistory(created.id), isEmpty);
    } finally {
      await deleteRoutine(created.id);
    }
    final after = await fetchRoutines(agentId: agent.id);
    expect(after.map((r) => r.id), isNot(contains(created.id)));
  }, skip: skip);

  test(
    'skills: catalog reads; an owner skill is added, switched and deleted',
    () async {
      final page = await fetchSkillCatalog(agent.id);
      expect(page.items, isNotEmpty);
      final first = await fetchSkillDetail(agent.id, page.items.first.id);
      expect(first.content, isNotNull);
      final controls = await fetchSkillControls(agent.id);
      expect(controls.revision, isA<int>());
      final id =
          'android-check-${DateTime.now().millisecondsSinceEpoch % 100000}';
      final created = await createSkill(
        agent.id,
        newSkillPayload(
          id: id,
          title: 'Android check',
          purpose: 'A disposable check.',
          version: '1.0.0',
          content: 'Do nothing.',
        ),
      );
      try {
        expect(created.enabled, isTrue);
        final off = await saveSkill(created, {
          ...created.payload,
          'enabled': false,
        });
        expect(off.enabled, isFalse);
        expect(off.version, created.version + 1);
        final versions = await fetchSkillVersions(created.id);
        expect(versions.length, greaterThanOrEqualTo(2));
        final installed = await fetchInstalledSkills(agent.id);
        expect(installed.map((s) => s.id), contains(created.id));
      } finally {
        await deleteSkill(created.id);
      }
      final after = await fetchInstalledSkills(agent.id);
      expect(after.map((s) => s.id), isNot(contains(created.id)));
    },
    skip: skip,
  );

  test('tasks read', () async {
    final tasks = await fetchTasks();
    for (final t in tasks) {
      expect(t.id, isNotEmpty);
      expect(t.version, greaterThanOrEqualTo(1));
    }
  }, skip: skip);
}
