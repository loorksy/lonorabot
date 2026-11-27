import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/voice/call_overlay.dart';
import 'package:lonora/features/voice/incoming_call.dart';
import 'package:lonora/features/voice/voice_api.dart';
import 'package:lonora/features/voice/voice_note_button.dart';
import 'package:lonora/features/voice/voice_note_machine.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../design/harness.dart';
import '../../platform/platform_harness.dart';
import 'voice_fakes.dart';

final now = DateTime.utc(2026, 11, 27, 10, 0, 0);

VoiceCallState connected({bool muted = false}) => VoiceCallState(
  phase: CallPhase.connected,
  agentId: 'a-sara',
  threadId: 't-sara',
  startedAt: now.subtract(const Duration(seconds: 80)),
  connectedAt: now.subtract(const Duration(seconds: 72)),
  speaking: true,
  level: 0.55,
  muted: muted,
);

class FakeRecorder implements VoiceNoteRecorder {
  PermissionStatus status = PermissionStatus.granted;
  final levelsOut = StreamController<double>.broadcast();
  String? started;
  bool stopped = false;
  bool cancelled = false;
  bool disposed = false;
  Future<void>? startGate;

  @override
  Future<PermissionStatus> permission() async => status;
  @override
  Future<void> start(String path) async {
    await startGate;
    started = path;
  }

  @override
  Future<String?> stop() async {
    stopped = true;
    return started;
  }

  @override
  Future<void> cancel() async => cancelled = true;
  @override
  Future<void> pause() async {}
  @override
  Future<void> resume() async {}
  @override
  Stream<double> levels() => levelsOut.stream;
  @override
  Future<void> dispose() async => disposed = true;
}

void main() {
  setUpAll(setUpPlatformTests);

  test('callClock and the status line', () {
    expect(callClock(const Duration(seconds: 72)), '01:12');
    expect(callClock(const Duration(hours: 1, seconds: 3)), '1:00:03');
    expect(callClock(const Duration(seconds: -3)), '00:00');
    final l10n = platformL10n..setLocale(const Locale('en'));
    expect(
      callStatus(l10n, const VoiceCallState(phase: CallPhase.calling)),
      'Calling…',
    );
    expect(callStatus(l10n, connected(muted: true)), 'Microphone muted');
    expect(callStatus(l10n, connected()), l10n.t('callSpeaking'));
    expect(
      callStatus(l10n, const VoiceCallState(phase: CallPhase.ended)),
      'Call ended',
    );
    // A call that never connected did not end: the error card speaks.
    expect(
      callStatus(
        l10n,
        const VoiceCallState(
          phase: CallPhase.failed,
          error: 'voice_permission_denied',
        ),
      ),
      '',
    );
    expect(
      callStatus(
        l10n,
        connected().copyWith(
          phase: CallPhase.failed,
          error: 'voice_connection_failed',
        ),
      ),
      'Call ended',
    );
  });

  test('incoming calls: the first ringing, unexpired one; accepts that authorize nothing', () {
    final rows = [
      {'id': 'a', 'status': 'missed', 'expires_at': '2026-11-27T10:05:00Z'},
      {'id': 'b', 'status': 'ringing', 'expires_at': '2026-11-27T09:59:00Z'},
      {'id': 'c', 'status': 'ringing', 'expires_at': '2026-11-27T10:00:30Z'},
    ];
    expect(visibleIncoming(rows, now)?['id'], 'c');
    expect(
      acceptedIncoming({
        'status': 'accepted',
        'expires_at': '2026-11-27T10:00:30Z',
        'execution_authorized': false,
      }, now),
      isTrue,
    );
    expect(
      acceptedIncoming({
        'status': 'accepted',
        'expires_at': '2026-11-27T10:00:30Z',
        'execution_authorized': true,
      }, now),
      isFalse,
    );
  });

  for (final v in platformVariants) {
    testWidgets('call page golden ${v.name}', (tester) async {
      setPlatformViewport(tester);
      final store = voiceStore();
      await withRealShadows(() async {
        await tester.pumpWidget(
          platformApp(
            store: store,
            dark: v.dark,
            locale: v.locale,
            home: VoiceCallView(
              state: connected(),
              agent: store.state.shell.agents['a-sara'],
              now: now,
              animate: false,
            ),
          ),
        );
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/call_connected_${v.name}.png'),
        );
      });
    });

    testWidgets('pill, incoming call and voice-note bars ${v.name}', (
      tester,
    ) async {
      setPlatformViewport(tester);
      final store = voiceStore();
      final sara = store.state.shell.agents['a-sara'];
      final recording = VoiceNoteMachine()
        ..down()
        ..holdElapsed()
        ..tick(7.4)
        ..move(v.locale == 'ar' ? 30 : -30, 0, rtl: v.locale == 'ar');
      final locked = VoiceNoteMachine()
        ..down()
        ..holdElapsed()
        ..move(0, -80, rtl: false)
        ..tick(23.6);
      for (var i = 0; i < 40; i++) {
        locked.level((i * 37 % 100) / 100);
      }
      await withRealShadows(() async {
        await tester.pumpWidget(
          platformApp(
            store: store,
            dark: v.dark,
            locale: v.locale,
            home: BackdropPage(
              children: [
                Positioned(
                  top: 26,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: CallPill(state: connected(), agent: sara, now: now),
                  ),
                ),
                Positioned(
                  top: 140,
                  left: 16,
                  right: 16,
                  child: IncomingCallView(
                    reason: v.locale == 'ar'
                        ? 'الذهب كسر مستوى 2,400 وأحتاج قرارك بشأن الأمر المعلّق.'
                        : 'Gold broke 2,400 and I need your call on the pending order.',
                    agent: sara,
                  ),
                ),
                Positioned(
                  left: 20,
                  right: 20,
                  bottom: 120,
                  height: 48,
                  child: VoiceNoteBar(machine: recording),
                ),
                Positioned(
                  left: 20,
                  right: 20,
                  bottom: 40,
                  height: 48,
                  child: VoiceNoteBar(machine: locked),
                ),
              ],
            ),
          ),
        );
        await tester.pump(const Duration(milliseconds: 400));
        await expectLater(
          find.byType(WidgetsApp),
          matchesGoldenFile('goldens/call_pill_incoming_notes_${v.name}.png'),
        );
      });
    });
  }

  testWidgets('call states: calling and failed (light ar, dark en)', (
    tester,
  ) async {
    setPlatformViewport(tester);
    final store = voiceStore();
    await withRealShadows(() async {
      await tester.pumpWidget(
        platformApp(
          store: store,
          locale: 'ar',
          home: VoiceCallView(
            state: VoiceCallState(
              phase: CallPhase.calling,
              agentId: 'a-sara',
              threadId: 't-sara',
              startedAt: now,
            ),
            agent: store.state.shell.agents['a-sara'],
            now: now,
            animate: false,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(WidgetsApp),
        matchesGoldenFile('goldens/call_calling_light_ar.png'),
      );
      await tester.pumpWidget(
        platformApp(
          store: store,
          dark: true,
          locale: 'en',
          home: VoiceCallView(
            state: const VoiceCallState(
              phase: CallPhase.failed,
              agentId: 'a-sara',
              threadId: 't-sara',
              error: 'voice_permission_denied',
              openSettings: true,
            ),
            agent: store.state.shell.agents['a-sara'],
            now: now,
            animate: false,
            onClose: () {},
            onOpenSettings: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(WidgetsApp),
        matchesGoldenFile('goldens/call_failed_dark_en.png'),
      );
    });
  });

  for (final locale in ['ar', 'en']) {
    testWidgets(
      'text at 1.3×: call page, pill, incoming call, bars ($locale)',
      (tester) async {
        setPlatformViewport(tester);
        tester.platformDispatcher.textScaleFactorTestValue = 1.3;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final store = voiceStore();
        final sara = store.state.shell.agents['a-sara'];
        for (final state in [
          connected(),
          connected(muted: true),
          const VoiceCallState(
            phase: CallPhase.failed,
            agentId: 'a-sara',
            threadId: 't-sara',
            error: 'voice_transport_unconfigured',
          ),
        ]) {
          await tester.pumpWidget(
            platformApp(
              store: store,
              locale: locale,
              home: VoiceCallView(
                state: state,
                agent: sara,
                now: now,
                animate: false,
                onRetry: () {},
                onClose: () {},
              ),
            ),
          );
          await tester.pump(const Duration(milliseconds: 400));
          expect(tester.takeException(), isNull);
        }
        final locked = VoiceNoteMachine()
          ..down()
          ..holdElapsed()
          ..move(0, -80, rtl: false)
          ..tick(83.2);
        await tester.pumpWidget(
          platformApp(
            store: store,
            locale: locale,
            home: BackdropPage(
              children: [
                Positioned(
                  top: 26,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: CallPill(state: connected(), agent: sara, now: now),
                  ),
                ),
                Positioned(
                  top: 140,
                  left: 16,
                  right: 16,
                  child: IncomingCallView(
                    reason: locale == 'ar'
                        ? 'الذهب كسر مستوى 2,400 وأحتاج قرارك بشأن الأمر المعلّق قبل الإغلاق.'
                        : 'Gold broke 2,400 and I need your call on the pending order before the close.',
                    agent: sara,
                    error: 'voice_connection_failed',
                  ),
                ),
                Positioned(
                  left: 20,
                  right: 20,
                  bottom: 40,
                  height: 48,
                  child: VoiceNoteBar(machine: locked),
                ),
              ],
            ),
          ),
        );
        await tester.pump(const Duration(milliseconds: 400));
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets('the call page controls reach the controller', (tester) async {
    setPlatformViewport(tester);
    final store = voiceStore();
    var minimized = 0, ended = 0, muted = 0, speaker = 0;
    await tester.pumpWidget(
      platformApp(
        store: store,
        locale: 'en',
        home: VoiceCallView(
          state: connected(),
          agent: store.state.shell.agents['a-sara'],
          now: now,
          animate: false,
          onMinimize: () => minimized++,
          onEnd: () => ended++,
          onMute: () => muted++,
          onSpeaker: () => speaker++,
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel(platformL10n.t('endCall')));
    await tester.tap(find.bySemanticsLabel(platformL10n.t('muteCall')));
    await tester.tap(find.bySemanticsLabel('Speaker'));
    await tester.tap(find.text('Minimize'));
    await tester.pump(const Duration(milliseconds: 300));
    expect((ended, muted, speaker, minimized), (1, 1, 1, 1));
    expect(find.text('Voice call · \u206601:12\u2069'), findsOneWidget);
  });

  group('VoiceNoteButton', () {
    late FakeRecorder recorder;
    late List<({String threadId, double seconds, List<int> peaks})> sent;

    setUp(() {
      recorder = FakeRecorder();
      sent = [];
      VoiceNoteButton.recorderFactory = () => recorder;
      VoiceNoteButton.recordingsDir = () async => '/tmp';
      VoiceNoteButton.sender =
          (
            context, {
            required threadId,
            required path,
            required seconds,
            required peaks,
          }) async =>
              sent.add((threadId: threadId, seconds: seconds, peaks: peaks));
    });

    Future<List<bool>> pumpButton(WidgetTester tester) async {
      setPlatformViewport(tester);
      final changes = <bool>[];
      await tester.pumpWidget(
        platformApp(
          store: voiceStore(),
          locale: 'en',
          home: Align(
            alignment: Alignment.bottomRight,
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: VoiceNoteButton(
                threadId: 't-sara',
                onRecordingChanged: changes.add,
              ),
            ),
          ),
        ),
      );
      return changes;
    }

    testWidgets('hold, speak, release: uploads and sends the note', (
      tester,
    ) async {
      final changes = await pumpButton(tester);
      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(VoiceNoteButton)),
      );
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pump();
      expect(changes, [true]);
      expect(recorder.started, isNotNull);
      expect(find.text('Slide to cancel'), findsOneWidget);
      for (var i = 0; i < 30; i++) {
        recorder.levelsOut.add(i.isEven ? 0.8 : 0.2);
        await tester.pump(const Duration(milliseconds: 100));
      }
      await gesture.up();
      await tester.pump();
      await tester.pump();
      expect(recorder.stopped, isTrue);
      expect(changes, [true, false]);
      expect(sent, hasLength(1));
      expect(sent.single.threadId, 't-sara');
      expect(sent.single.seconds, closeTo(3.0, 0.11));
      expect(sent.single.peaks, hasLength(44));
      expect(find.text('Slide to cancel'), findsNothing);
    });

    testWidgets('slide toward the start cancels; nothing is sent', (
      tester,
    ) async {
      await pumpButton(tester);
      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(VoiceNoteButton)),
      );
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pump(const Duration(seconds: 2));
      await gesture.moveBy(const Offset(-60, 0));
      await gesture.moveBy(const Offset(-60, 0));
      await tester.pump();
      await gesture.up();
      await tester.pump();
      expect(recorder.cancelled, isTrue);
      expect(sent, isEmpty);
    });

    testWidgets('slide up locks; the bar sends without the finger', (
      tester,
    ) async {
      await pumpButton(tester);
      final gesture = await tester.startGesture(
        tester.getCenter(find.byType(VoiceNoteButton)),
      );
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pump(const Duration(seconds: 1));
      await gesture.moveBy(const Offset(0, -80));
      await gesture.up();
      await tester.pump(const Duration(seconds: 1));
      expect(find.bySemanticsLabel('Send the voice message'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Send the voice message'));
      await tester.pump();
      await tester.pump();
      expect(sent, hasLength(1));
      expect(sent.single.seconds, closeTo(2.0, 0.11));
      await tester.pump(const Duration(seconds: 3));
    });

    for (final locale in ['en', 'ar']) {
      testWidgets(
        'the bar stays on the mic when the keyboard closes under the finger ($locale)',
        (tester) async {
          setPlatformViewport(tester);
          // The keyboard is up (300 dp) when the owner presses the mic.
          tester.view.viewInsets = const FakeViewPadding(bottom: 600);
          addTearDown(tester.view.resetViewInsets);
          await tester.pumpWidget(
            platformApp(
              store: voiceStore(),
              locale: locale,
              home: Builder(
                builder: (context) => Padding(
                  padding: EdgeInsets.only(
                    bottom: MediaQuery.viewInsetsOf(context).bottom,
                  ),
                  child: const Align(
                    alignment: AlignmentDirectional.bottomEnd,
                    child: Padding(
                      padding: EdgeInsets.all(20),
                      child: VoiceNoteButton(threadId: 't-sara'),
                    ),
                  ),
                ),
              ),
            ),
          );
          final gesture = await tester.startGesture(
            tester.getCenter(find.byType(VoiceNoteButton)),
          );
          await tester.pump(const Duration(milliseconds: 400));
          await tester.pump();
          final width =
              tester.view.physicalSize.width / tester.view.devicePixelRatio;
          Rect mic() => tester.getRect(find.byType(VoiceNoteButton));
          Rect bar() => tester.getRect(find.byType(VoiceNoteBar));
          void onMic(Rect m) {
            expect(bar().bottom, closeTo(m.bottom + 1, 0.01));
            if (locale == 'ar') {
              expect(bar().left, closeTo(m.left - 1, 0.01));
              expect(bar().right, closeTo(width - LnSpace.chromeGutter, 0.01));
            } else {
              expect(bar().right, closeTo(m.right + 1, 0.01));
              expect(bar().left, closeTo(LnSpace.chromeGutter, 0.01));
            }
          }

          final before = mic();
          onMic(before);
          // The composer disables its field: the keyboard closes and the composer drops.
          tester.view.viewInsets = FakeViewPadding.zero;
          await tester.pump();
          final after = mic();
          expect(after.bottom, greaterThan(before.bottom + 200));
          onMic(after);
          await gesture.up();
          await tester.pump();
          await tester.pump();
        },
      );
    }

    testWidgets(
      'leaving while the microphone opens releases it and sends nothing',
      (tester) async {
        final opening = Completer<void>();
        recorder.startGate = opening.future;
        final changes = await pumpButton(tester);
        final gesture = await tester.startGesture(
          tester.getCenter(find.byType(VoiceNoteButton)),
        );
        await tester.pump(const Duration(milliseconds: 400));
        await tester.pump();
        expect(changes, [true]);
        // The conversation closes before the microphone answers.
        await tester.pumpWidget(
          platformApp(
            store: voiceStore(),
            locale: 'en',
            home: const SizedBox(),
          ),
        );
        expect(recorder.cancelled, isFalse, reason: 'start still in flight');
        opening.complete();
        await tester.pump();
        await tester.pump();
        expect(recorder.cancelled, isTrue);
        expect(recorder.disposed, isTrue);
        expect(changes, [true, false], reason: 'told after the frame');
        await gesture.up();
        await tester.pump(const Duration(seconds: 1));
        expect(sent, isEmpty);
      },
    );

    testWidgets(
      'a tap only reminds how it works; microphone refused shows why',
      (tester) async {
        final changes = await pumpButton(tester);
        await tester.tap(find.byType(VoiceNoteButton));
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.text(platformL10n.t('vn_holdHint')), findsOneWidget);
        expect(changes, isEmpty);
        await tester.pump(const Duration(seconds: 3));

        recorder.status = PermissionStatus.denied;
        final gesture = await tester.startGesture(
          tester.getCenter(find.byType(VoiceNoteButton)),
        );
        await tester.pump(const Duration(milliseconds: 400));
        await tester.pump();
        await gesture.up();
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.text(platformL10n.t('vn_micDenied')), findsOneWidget);
        expect(recorder.started, isNull);
        expect(changes, [true, false]);
        await tester.pump(const Duration(seconds: 3));
      },
    );
  });

  test('VoiceCalls keeps its public API', () {
    expect(VoiceCalls.active.value, isFalse);
    expect(L10n.supportedLocales, isNotEmpty);
  });
}
