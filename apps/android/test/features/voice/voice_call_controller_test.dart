import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/features/cards/cards_actions.dart';
import 'package:lonora/features/voice/voice_api.dart';
import 'package:lonora/features/voice/voice_transport.dart';
import 'package:lonora/state/actions/thread_actions.dart';
import 'package:lonora/state/app_state.dart';

import 'voice_fakes.dart';

void main() {
  late FakeApi api;
  late FakeTransport? transport;
  late List<bool> awake;
  late List<String> ongoing;
  late int hidden;
  late Store<AppState> store;
  late List<bool> proximity;
  var mic = MicPermission.granted;

  VoiceCallController controller({
    Duration approvalsEvery = const Duration(hours: 1),
  }) {
    api = FakeApi()
      ..on('GET /voice/status', (_) => {'transport_configured': true})
      ..on('GET /trading/approvals', (_) => const []);
    transport = null;
    awake = [];
    ongoing = [];
    hidden = 0;
    proximity = [];
    store = voiceStore();
    return VoiceCallController(
      api: () => api,
      store: () => store,
      transport: (callbacks, client) =>
          transport = FakeTransport(callbacks, client),
      microphone: () async => mic,
      keepAwake: (on) async => awake.add(on),
      showOngoing: (s) async => ongoing.add(s.phase.name),
      hideOngoing: () async => hidden++,
      proximity: (on) async => proximity.add(on),
      endedLinger: const Duration(milliseconds: 20),
      approvalsEvery: approvalsEvery,
    );
  }

  setUp(() => mic = MicPermission.granted);

  test(
    'Calling… → connected → ended → idle, with wakelock and notification',
    () async {
      final c = controller();
      await c.start(agentId: 'a-sara', threadId: 't-sara');
      expect(c.state.phase, CallPhase.calling);
      expect(VoiceCalls.active.value, isTrue);
      expect(transport!.connected, isTrue);
      expect(awake, [true]);
      expect(ongoing, ['calling']);

      transport!.callbacks.onConnected();
      expect(c.state.phase, CallPhase.connected);
      expect(c.state.connectedAt, isNotNull);
      expect(ongoing, ['calling', 'connected']);

      transport!.callbacks.onActivity(
        const VoiceActivity(speaking: true, level: 0.6),
      );
      expect(c.state.speaking, isTrue);
      expect(c.state.level, 0.6);

      await c.end();
      expect(transport!.closed, isTrue);
      expect(transport!.finalized, isTrue);
      expect(
        api.calls.map((x) => '${x.method} ${x.path}'),
        contains('DELETE /voice/sessions/s1'),
      );
      expect(c.state.phase, CallPhase.ended);
      expect(c.state.endedAfter, isNotNull);
      expect(VoiceCalls.active.value, isFalse);
      expect(awake, [true, false]);
      expect(hidden, 1);
      await Future<void>.delayed(const Duration(milliseconds: 40));
      expect(c.state.phase, CallPhase.idle);
    },
  );

  test('no voice provider: a clear error, no microphone', () async {
    final c = controller();
    api.on('GET /voice/status', (_) => {'transport_configured': false});
    await c.start(agentId: 'a-sara', threadId: 't-sara');
    expect(c.state.phase, CallPhase.failed);
    expect(c.state.error, 'voice_transport_unconfigured');
    expect(transport, isNull);
    expect(awake, isEmpty);
    expect(c.state.canRetry, isTrue);
  });

  test('microphone refused (for good: Settings)', () async {
    mic = MicPermission.permanentlyDenied;
    final c = controller();
    await c.start(agentId: 'a-sara', threadId: 't-sara');
    expect(c.state.error, 'voice_permission_denied');
    expect(c.state.openSettings, isTrue);
    expect(transport, isNull);
  });

  test(
    'a server refusal or a dropped peer fails the call and releases everything',
    () async {
      final c = controller();
      await c.start(agentId: 'a-sara', threadId: 't-sara');
      transport!.callbacks.onError('voice_connection_failed');
      expect(c.state.phase, CallPhase.failed);
      expect(c.state.minimized, isFalse);
      await Future<void>.delayed(Duration.zero);
      expect(transport!.closed, isTrue);
      expect(awake.last, isFalse);

      api.on(
        'GET /voice/status',
        (_) => ApiError(status: 409, code: 'agent_paused'),
      );
      c.dismiss();
      await c.start(agentId: 'a-sara', threadId: 't-sara');
      expect(c.state.error, 'agent_paused');
    },
  );

  test('a second start brings the running call back instead', () async {
    final c = controller();
    await c.start(agentId: 'a-sara', threadId: 't-sara');
    c.minimize();
    expect(c.state.minimized, isTrue);
    final first = transport;
    await c.start(agentId: 'a-other', threadId: 't-other');
    expect(transport, same(first));
    expect(c.state.minimized, isFalse);
    expect(c.state.agentId, 'a-sara');
  });

  test('mute and speaker reach the transport', () async {
    final c = controller();
    await c.start(agentId: 'a-sara', threadId: 't-sara');
    transport!.callbacks.onConnected();
    await c.toggleMute();
    expect(c.state.muted, isTrue);
    expect(transport!.muted, isTrue);
    await c.toggleSpeaker();
    expect(c.state.speaker, isFalse);
    expect(transport!.speaker, isFalse);
  });

  test('sign-out without a token closes on the phone only', () async {
    final c = controller();
    await c.start(agentId: 'a-sara', threadId: 't-sara');
    await c.end(finalize: false);
    expect(transport!.finalized, isFalse);
    expect(api.calls.where((x) => x.method == 'DELETE'), isEmpty);
  });

  test('an answered incoming call joins with its id', () async {
    final c = controller();
    await c.start(
      agentId: 'a-sara',
      threadId: 't-sara',
      incomingCallId: 'ic-1',
    );
    expect(transport!.incomingCallId, 'ic-1');
  });

  test(
    'pending trade approvals of the conversation are shown under the controls',
    () async {
      final c = controller();
      final since = DateTime.now().toUtc();
      api.on(
        'GET /trading/approvals',
        (_) => [
          {
            'id': 'old',
            'status': 'approved',
            'created_at': since
                .subtract(const Duration(hours: 1))
                .toIso8601String(),
          },
          {
            'id': 'p1',
            'status': 'pending',
            'created_at': since
                .subtract(const Duration(hours: 1))
                .toIso8601String(),
          },
          {
            'id': 'new',
            'status': 'rejected',
            'created_at': since
                .add(const Duration(seconds: 5))
                .toIso8601String(),
          },
        ],
      );
      await c.start(agentId: 'a-sara', threadId: 't-sara');
      await Future<void>.delayed(Duration.zero);
      expect(c.state.approvalIds, ['p1', 'new']);
    },
  );

  test(
    'a late read never takes a card the owner decided back to pending',
    () async {
      final c = controller(approvalsEvery: const Duration(milliseconds: 5));
      final created = DateTime.now()
          .toUtc()
          .subtract(const Duration(hours: 1))
          .toIso8601String();
      api.on(
        'GET /trading/approvals',
        (_) => [
          {'id': 'p1', 'status': 'pending', 'created_at': created},
        ],
      );
      await c.start(agentId: 'a-sara', threadId: 't-sara');
      await Future<void>.delayed(Duration.zero);
      expect(c.state.approvalIds, ['p1']);
      // The owner approves on the card (TradeApprovalDecisionAction writes the merged row);
      // reads that left before the tap still answer «pending».
      store.dispatch(
        PatchThreadAction(
          't-sara',
          (t) => t.copyWith(
            side: {
              ...t.side,
              SideKeys.approvals: [
                {'id': 'p1', 'status': 'approved', 'created_at': created},
              ],
            },
          ),
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 30));
      final rows = sideList(store.state.thread('t-sara'), SideKeys.approvals);
      expect(rows.single['status'], 'approved');
      // The card the call showed stays under the controls, decided.
      expect(c.state.approvalIds, ['p1']);
      await c.end();
    },
  );

  test('the earpiece turns the screen off at the ear; the speaker and the end release it', () async {
    final c = controller();
    await c.start(agentId: 'a-sara', threadId: 't-sara');
    transport!.callbacks.onConnected();
    expect(proximity, isEmpty);
    await c.toggleSpeaker();
    expect(proximity, [true]);
    await c.toggleSpeaker();
    expect(proximity, [true, false]);
    await c.toggleSpeaker();
    await c.end();
    expect(proximity, [true, false, true, false]);
  });
}
