// PlatformServices against a real store and fakes: the background check's heartbeat (and
// none while the app is away), an opened conversation's notification, the notification
// prompt asked once, and sign-out.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/features/voice/incoming_call.dart';
import 'package:lonora/features/voice/voice_api.dart';
import 'package:lonora/platform/background/poll_logic.dart';
import 'package:lonora/platform/background/poll_store.dart';
import 'package:lonora/platform/heads_up.dart';
import 'package:lonora/platform/heads_up/heads_up_controller.dart';
import 'package:lonora/state/actions/session_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../features/voice/voice_fakes.dart';
import 'platform_fixtures.dart';
import 'platform_harness.dart';

class _Set extends ReduxAction<AppState> {
  _Set(this.change);
  final AppState Function(AppState) change;
  @override
  AppState reduce() => change(state);
}

const _permissions = MethodChannel('flutter.baseflow.com/permissions/methods');

void main() {
  setUpAll(setUpPlatformTests);

  late Store<AppState> app;
  late FakeApi api;
  late MemoryPollStore polls;
  late List<(String, int)> cancelled;
  late List<String> asked;
  late FakeTransport? transport;
  var now = t0;

  Future<void> boot(WidgetTester tester) async {
    await sl.reset();
    api = FakeApi()
      ..on('GET /voice/status', (_) => {'transport_configured': true});
    app = Store<AppState>(
      initialState: AppState(
        session: const SessionState(
          status: SessionStatus.signedIn,
          server: 'https://lonora.example.com',
          owner: Owner(id: 'owner-1', email: 'o@example.com'),
        ),
        shell: demoShell(),
      ),
    );
    sl.registerSingleton<Store<AppState>>(app);
    sl.registerSingleton<ApiClient>(api);
    sl.registerSingleton<SharedPreferences>(
      await SharedPreferences.getInstance(),
    );
    realtime = RealtimeController(app);
    polls = MemoryPollStore();
    cancelled = [];
    asked = [];
    transport = null;
    now = t0;
    PlatformServices.store = polls;
    PlatformServices.clock = () => now;
    PlatformServices.cancelThread = (id, remaining) async =>
        cancelled.add((id, remaining));
    VoiceCalls.controller = VoiceCallController(
      api: () => api,
      store: () => app,
      transport: (c, a) => transport = FakeTransport(c, a),
      microphone: () async => MicPermission.granted,
      keepAwake: (_) async {},
      showOngoing: (_) async {},
      hideOngoing: () async {},
      proximity: (_) async {},
      endedLinger: const Duration(milliseconds: 10),
      approvalsEvery: const Duration(hours: 1),
    );
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      _permissions,
      (call) async {
        asked.add(call.method);
        return switch (call.method) {
          'checkPermissionStatus' => 0, // denied, not for good
          'requestPermissions' => {17: 1},
          _ => null,
        };
      },
    );
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await PlatformServices.init();
    for (var i = 0; i < 5; i++) {
      await tester.pump();
    }
  }

  /// The services' timers stop inside the test body (the binding checks for pending
  /// timers before tear-downs run); the rest is reset after it.
  void stopTimers() {
    HeadsUpController.instance.stop();
    IncomingCallController.instance.stop();
  }

  Future<void> shutdown(WidgetTester tester) async {
    stopTimers();
    await PlatformServices.resetForTest();
    PlatformServices.cancelThread = (_, _) async {};
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      _permissions,
      null,
    );
    VoiceCalls.active.value = false;
  }

  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets(
    'the heartbeat marks the app present; a refresh while it is away writes nothing',
    (tester) async {
      await boot(tester);
      addTearDown(() => shutdown(tester));
      expect(polls.state?.foregroundAt, t0);
      expect(polls.state?.ownerId, 'owner-1');

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump();
      expect(polls.state?.foregroundAt, isNull);
      final cursors = polls.state!.seqs;

      // A late shell refresh (or a call keeping the process alive) lands in the background.
      now = t0.add(const Duration(minutes: 2));
      final newer = InboxEntry.fromJson(
        inboxJson(
          't-sara',
          agentId: 'a-sara',
          unread: 1,
          last: lastMessage(id: 'm50', seq: 50, agentId: 'a-sara'),
        ),
      );
      app.dispatch(
        _Set(
          (s) => s.copyWith(
            shell: s.shell.copyWith(inbox: [newer, ...s.shell.inbox.skip(1)]),
          ),
        ),
      );
      await tester.pump();
      expect(polls.state?.foregroundAt, isNull, reason: 'not present');
      expect(polls.state?.seqs, cursors, reason: 'cursors not advanced');

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(polls.state?.foregroundAt, now);
      expect(polls.state?.seqs['t-sara'], 50);
      stopTimers();
    },
  );

  testWidgets('an opened conversation loses its notification and lines; the summary goes with the '
      'last one', (tester) async {
    await boot(tester);
    addTearDown(() => shutdown(tester));
    const line = [NoteLine('Earlier')];
    polls.state = polls.state!.copyWith(
      notified: const {'t-sara': line, 't-omar': line},
    );

    app.dispatch(_Set((s) => s.copyWith(openThreadId: 't-sara')));
    await tester.pump();
    expect(cancelled, [('t-sara', 1)]);
    expect(polls.state!.notified.keys, ['t-omar']);

    app.dispatch(_Set((s) => s.copyWith(openThreadId: 't-omar')));
    await tester.pump();
    expect(cancelled.last, ('t-omar', 0));
    expect(polls.state!.notified, isEmpty);
    stopTimers();
  });

  testWidgets('the notification prompt is asked once', (tester) async {
    await boot(tester);
    addTearDown(() => shutdown(tester));
    expect(asked, ['checkPermissionStatus', 'requestPermissions']);
    expect(devicePrefs.getBool('lonora.notifications.asked'), isTrue);
    stopTimers();
  });

  testWidgets('a prompt already asked is not shown again', (tester) async {
    SharedPreferences.setMockInitialValues({
      'lonora.notifications.asked': true,
    });
    await boot(tester);
    addTearDown(() => shutdown(tester));
    expect(asked, isEmpty);
    stopTimers();
  });

  testWidgets(
    'sign-out ends the call, stops the services and forgets the cursor',
    (tester) async {
      await boot(tester);
      addTearDown(() => shutdown(tester));
      await VoiceCalls.controller.start(agentId: 'a-sara', threadId: 't-sara');
      expect(VoiceCalls.active.value, isTrue);
      expect(polls.state, isNotNull);

      // As SignOutAction runs them: the token is already gone.
      for (final hook in List.of(signOutHooks)) {
        await hook();
      }
      expect(transport!.closed, isTrue);
      expect(transport!.finalized, isFalse);
      expect(VoiceCalls.active.value, isFalse);
      expect(polls.state, isNull);
      expect(HeadsUpController.instance.current.value, isNull);
      await tester.pump(const Duration(milliseconds: 20));
      stopTimers();
    },
  );
}
