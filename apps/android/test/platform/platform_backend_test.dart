// WP-G against a REAL Lonora server (no API mocks): the background check's endpoints and
// cursor, the heads-up rules on real event envelopes, delivery rules, the voice status /
// incoming-call endpoints, and a voice-note upload (deleted again in the same test).
//
// Runs only when LONORA_TEST_CREDS points at a JSON file {server_url, owner_email,
// owner_password} of a disposable test server. Never point it at production. Writes: one
// login session (logged out at the end) and one uploaded artifact (deleted at the end).
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:async_redux/async_redux.dart';
import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/core/storage/local_store.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/features/voice/incoming_call.dart';
import 'package:lonora/features/voice/voice_api.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/platform/background/background_sync.dart';
import 'package:lonora/platform/background/poll_logic.dart';
import 'package:lonora/platform/background/poll_store.dart';
import 'package:lonora/platform/heads_up/heads_up_rules.dart';
import 'package:lonora/state/app_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../features/voice/voice_fakes.dart' show FakeTransport;

class _Secure extends SecureStore {
  StoredSession? session;
  @override
  Future<StoredSession?> readSession() async => session;
}

/// A 1 s 8 kHz mono WAV tone (the server accepts `audio/wav` voice notes).
Uint8List wavTone() {
  const rate = 8000;
  final samples = Int16List(rate);
  for (var i = 0; i < rate; i++) {
    samples[i] = ((i % 40) < 20 ? 6000 : -6000);
  }
  final data = samples.buffer.asUint8List();
  final header = ByteData(44);
  void ascii(int at, String s) {
    for (var i = 0; i < s.length; i++) {
      header.setUint8(at + i, s.codeUnitAt(i));
    }
  }

  ascii(0, 'RIFF');
  header.setUint32(4, 36 + data.length, Endian.little);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  header.setUint32(16, 16, Endian.little);
  header.setUint16(20, 1, Endian.little);
  header.setUint16(22, 1, Endian.little);
  header.setUint32(24, rate, Endian.little);
  header.setUint32(28, rate * 2, Endian.little);
  header.setUint16(32, 2, Endian.little);
  header.setUint16(34, 16, Endian.little);
  ascii(36, 'data');
  header.setUint32(40, data.length, Endian.little);
  return Uint8List.fromList([...header.buffer.asUint8List(), ...data]);
}

void main() {
  final credsPath = Platform.environment['LONORA_TEST_CREDS'];
  final creds = credsPath != null && File(credsPath).existsSync()
      ? asJson(jsonDecode(File(credsPath).readAsStringSync()))
      : null;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    HttpOverrides.global = null; // real network for this test
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('ai.lonora.android/platform'),
          (call) async => null,
        );
    SharedPreferences.setMockInitialValues({});
    final dir = await Directory.systemTemp.createTemp('lonora_wpg');
    await registerServices(
      apiClient: ApiClient(userAgent: 'Lonora-Android/test'),
      secure: _Secure(),
      local: LocalStore.at(dir),
      prefs: await SharedPreferences.getInstance(),
      info: const AppInfo(
        version: '1.0.0',
        buildNumber: '1',
        packageName: 'ai.lonora.android',
      ),
    );
  });

  test(
    'background check, heads-up rules, voice endpoints and a voice-note upload',
    () async {
      final server = asStr(creds!['server_url']);
      final login = asJson(
        await api.probe(
          server,
          '/auth/mobile/login',
          method: 'POST',
          body: {
            'email': asStr(creds['owner_email']),
            'password': asStr(creds['owner_password']),
          },
        ),
      );
      final token = asStr(login['token']);
      final ownerId = asStr(asJson(login['owner'])['id']);
      expect(token, isNotEmpty);
      api.configure(server: server, token: token);
      String? uploaded;
      try {
        // ── Background check over real HTTP (the device client, minus storage). ──
        final dio = Dio(BaseOptions(validateStatus: (_) => true));
        final store = MemoryPollStore();
        final shown = <PlannedNotification>[];
        final l10n = await L10n.load();
        BackgroundCheckDeps deps(DateTime now) => BackgroundCheckDeps(
          readSession: () async => StoredSession(
            server: server,
            token: token,
            ownerId: ownerId,
            email: '',
          ),
          get: (s, t, path) async {
            final r = await dio.get<Object?>(
              '$s/api$path',
              options: Options(headers: {'Authorization': 'Bearer $t'}),
            );
            final status = r.statusCode ?? 0;
            if (status < 200 || status >= 300) {
              throw BackgroundHttpError(status);
            }
            return r.data;
          },
          store: store,
          l10n: (_) async => l10n,
          show: (note, _, _) async => shown.add(note),
          cancelThread: (_, _) async {},
          cancelAttention: (_) async {},
          cancelSchedule: () async {},
          now: () => now,
          appInForeground: () => false,
        );
        expect(
          await runBackgroundCheck(deps(DateTime.now())),
          BackgroundOutcome.baseline,
        );
        final baseline = store.state!;
        expect(baseline.ownerId, ownerId);
        expect(baseline.seqs, isNotEmpty);
        expect(
          await runBackgroundCheck(deps(DateTime.now())),
          BackgroundOutcome.checked,
        );
        expect(shown, isEmpty, reason: 'nothing changed since the baseline');

        // The same real rows with an older cursor: every urgent item announces itself.
        final inbox = asJsonList(await api.get('/threads/inbox'));
        final attention = asJsonList(await api.get('/attention'));
        final replay = computePoll(
          baseline.copyWith(
            since: DateTime.utc(2000),
            seqs: const {},
            seenAttention: const [],
          ),
          inbox: inbox,
          attention: attention,
          now: DateTime.now(),
          newMessage: 'New message',
          attentionText: (code, _) => code,
        );
        final urgent = attention
            .where(
              (a) =>
                  attentionAlwaysShows(asString(a['importance'])) ||
                  pushAttentionCodes.contains(a['code']),
            )
            .length;
        expect(
          replay.notes.where((n) => n.kind == PlannedKind.attention).length,
          greaterThanOrEqualTo(urgent),
        );
        for (final n in replay.notes) {
          expect(n.body, isNotEmpty);
          expect(n.payload.location, startsWith('/'));
        }

        // ── Delivery rules. ──
        final profile = asJson(await api.get('/owner/profile'));
        expect(QuietHours.fromJson(profile['reach_me']), isNotNull);
        final rules = asJson(await api.get('/agents/notifications'));
        expect(DeliveryRules.offFrom(rules), isA<Set<String>>());

        // ── Heads-up rules on real event envelopes. ──
        final agents = asJsonList(await api.get('/agents'))
            .map(Agent.fromJson)
            .toList();
        final groups = asJsonList(await api.get('/groups'))
            .map(Group.fromJson)
            .toList();
        final shell = ShellState(
          agents: {for (final a in agents) a.id: a},
          agentOrder: [for (final a in agents) a.id],
          groups: {for (final g in groups) g.id: g},
          inbox: inbox.map(InboxEntry.fromJson).toList(),
        );
        final events = asJsonList(await api.get('/events'))
            .map(LonoraEvent.fromJson)
            .whereType<LonoraEvent>()
            .where(
              (e) =>
                  e.kind == 'message.created' &&
                  e.payload['role'] == 'assistant',
            )
            .toList();
        var banners = 0;
        for (final e in events) {
          final b = messageBanner(
            e,
            shell: shell,
            current: null,
            rules: const DeliveryRules(),
            openedAt: DateTime.utc(2000),
            now: DateTime.now(),
            newMessage: 'New message',
          );
          final entry = shell.entryFor(e.threadId ?? '');
          if (entry != null && !entry.muted && !entry.archived) {
            expect(b, isNotNull, reason: '${e.kind} ${e.threadId}');
            expect(b!.text, isNotEmpty);
            banners++;
          }
        }
        // ignore: avoid_print
        print(
          'WP-G backend: ${inbox.length} chats, ${attention.length} attention, '
          '${events.length} assistant events, $banners banners, '
          '${replay.notes.length} replayed notifications',
        );

        // ── Voice: status, a call refused for no provider, incoming calls. ──
        final status = asJson(await api.get('/voice/status'));
        expect(status['transport'], 'gpt_live');
        final appStore = Store<AppState>(
          initialState: AppState(
            session: SessionState(
              status: SessionStatus.signedIn,
              server: server,
              owner: Owner(id: ownerId, email: ''),
            ),
            shell: shell,
          ),
        );
        final calls = VoiceCallController(
          api: () => api,
          store: () => appStore,
          transport: FakeTransport.new,
          microphone: () async => MicPermission.granted,
          keepAwake: (_) async {},
          showOngoing: (_) async {},
          hideOngoing: () async {},
          approvalsEvery: const Duration(hours: 1),
        );
        final agent = agents.firstWhere((a) => !a.paused);
        final thread = shell.inbox
            .firstWhere(
              (e) => e.agentId == agent.id && e.groupId == null,
              orElse: () => shell.inbox.first,
            )
            .threadId;
        if (status['transport_configured'] != true) {
          await calls.start(agentId: agent.id, threadId: thread);
          expect(calls.state.phase, CallPhase.failed);
          expect(calls.state.error, 'voice_transport_unconfigured');
        }
        final incoming = IncomingCallController(
          api: () => api,
          pollEvery: const Duration(hours: 1),
        );
        incoming.start(appStore, const Stream.empty());
        await incoming.refresh();
        expect(incoming.call, isNull);
        incoming.stop();
        final pending = asJsonList(await api.get('/voice/incoming'));
        expect(visibleIncoming(pending, DateTime.now()), isNull);

        // ── Voice note upload (as the composer's mic does), then removed. ──
        final file = File(
          '${(await Directory.systemTemp.createTemp('wpg_voice')).path}/note.wav',
        )..writeAsBytesSync(wavTone());
        final row = asJson(
          await api.upload(
            '/artifacts/upload',
            filePath: file.path,
            fileName: 'voice-test.wav',
            mimeType: 'audio/wav',
            fields: {'thread_id': thread},
          ),
        );
        uploaded = asString(row['id']);
        expect(uploaded, isNotNull);
        expect(
          asStr(asJson(row['payload'])['media_type']),
          startsWith('audio/'),
        );
      } finally {
        if (uploaded != null) {
          await api.delete('/artifacts/$uploaded');
          // Removed again.
          await expectLater(api.get('/artifacts/$uploaded'), throwsA(anything));
        }
        await api.post('/auth/logout');
      }
    },
    skip: creds == null
        ? 'Set LONORA_TEST_CREDS to run against a disposable Lonora server'
        : false,
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
