import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/storage/secure_store.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/platform/background/background_sync.dart';
import 'package:lonora/platform/background/poll_logic.dart';
import 'package:lonora/platform/background/poll_store.dart';
import 'package:lonora/platform/heads_up/heads_up_rules.dart';
import 'package:lonora/state/app_state.dart';

import 'platform_fixtures.dart';

const server = 'https://lonora.example.com';
final session = StoredSession(
  server: server,
  token: 'secret-token-value',
  ownerId: 'owner-1',
  email: 'o@example.com',
  expiresAt: t0.add(const Duration(days: 1)),
);

class Harness {
  Harness({this.stored, this.foreground = false});

  StoredSession? stored;
  bool foreground;

  /// The session entry cannot be read now (a passing Keystore failure).
  bool unreadable = false;
  bool preview = true;
  final store = MemoryPollStore();
  final requests = <String>[];
  final shown = <PlannedNotification>[];
  final clearedThreads = <String>[];
  final clearedAttention = <String>[];
  int cancelled = 0;
  Object? Function(String path) answer = (_) => const [];
  late final l10n = L10n(
    ar: const {'newMessage': 'رسالة جديدة'},
    en: const {'newMessage': 'New message'},
  );

  BackgroundCheckDeps deps({DateTime? now}) => BackgroundCheckDeps(
    readSession: () async =>
        unreadable ? throw PlatformException(code: 'keystore') : stored,
    get: (s, token, path) async {
      expect(s, server);
      expect(token, 'secret-token-value');
      requests.add(path);
      final value = answer(path);
      if (value is Exception) throw value;
      return value;
    },
    store: store,
    l10n: (_) async => l10n,
    show: (note, _, _) async => shown.add(note),
    cancelThread: (id, _) async => clearedThreads.add(id),
    cancelAttention: (id) async => clearedAttention.add(id),
    cancelSchedule: () async => cancelled++,
    now: () => now ?? t0,
    appInForeground: () => foreground,
    showPreview: () async => preview,
  );
}

void main() {
  test('no session: the schedule stops and the cursor goes', () async {
    final h = Harness();
    h.store.state = baselineState(
      ownerId: 'owner-1',
      server: server,
      inbox: const [],
      attention: const [],
      now: t0,
    );
    expect(await runBackgroundCheck(h.deps()), BackgroundOutcome.noSession);
    expect(h.cancelled, 1);
    expect(h.store.state, isNull);
    expect(h.requests, isEmpty);
  });

  test(
    'an unreadable session is not none: no request, schedule and cursor kept',
    () async {
      final h = Harness(stored: session)..unreadable = true;
      final cursor = baselineState(
        ownerId: 'owner-1',
        server: server,
        inbox: const [],
        attention: const [],
        now: t0,
      );
      h.store.state = cursor;
      // The dispatcher catches it; the next period tries again.
      await expectLater(
        runBackgroundCheck(h.deps()),
        throwsA(isA<PlatformException>()),
      );
      expect(h.requests, isEmpty);
      expect(h.cancelled, 0);
      expect(h.store.state, same(cursor));
    },
  );

  test('an expired session counts as none', () async {
    final h = Harness(
      stored: StoredSession(
        server: server,
        token: 'secret-token-value',
        ownerId: 'owner-1',
        email: '',
        expiresAt: t0.subtract(const Duration(minutes: 1)),
      ),
    );
    expect(await runBackgroundCheck(h.deps()), BackgroundOutcome.noSession);
  });

  test(
    'skips while the app is in the foreground (live or heartbeat)',
    () async {
      final h = Harness(stored: session, foreground: true);
      expect(await runBackgroundCheck(h.deps()), BackgroundOutcome.foreground);
      h.foreground = false;
      h.store.state = baselineState(
        ownerId: 'owner-1',
        server: server,
        inbox: const [],
        attention: const [],
        now: t0,
      ).copyWith(foregroundAt: t0.subtract(const Duration(minutes: 1)));
      expect(await runBackgroundCheck(h.deps()), BackgroundOutcome.foreground);
      expect(h.requests, isEmpty);
    },
  );

  test('a session on a remote plain-http server gets no request', () async {
    final h = Harness(
      stored: StoredSession(
        server: 'http://lonora.example.com',
        token: 'secret-token-value',
        ownerId: 'owner-1',
        email: 'o@example.com',
      ),
    );
    expect(await runBackgroundCheck(h.deps()), BackgroundOutcome.noSession);
    expect(h.requests, isEmpty);
    expect(h.cancelled, 1);
  });

  test('text preview off: «New message», without words or speakers', () async {
    final h = Harness(stored: session)..preview = false;
    h.store.state = PollState(
      ownerId: 'owner-1',
      server: server,
      since: t0.subtract(const Duration(minutes: 20)),
      seqs: const {'t-desk': 7},
      titles: const {'t-desk': 'Desk'},
      agentNames: const {'a-omar': 'Omar'},
    );
    h.answer = (path) => path == '/threads/inbox'
        ? [
            inboxJson(
              't-desk',
              groupId: 'g-desk',
              unread: 1,
              last: lastMessage(
                id: 'm8',
                seq: 8,
                agentId: 'a-omar',
                content: 'Gold broke above the weekly range.',
              ),
            ),
          ]
        : [
            attentionJson(
              'a2',
              threadId: 't-desk',
              parameters: const {'summary': 'Approve the gold order?'},
            ),
          ];
    await runBackgroundCheck(h.deps(now: t0.add(const Duration(minutes: 1))));
    expect(h.shown.map((n) => n.kind), [
      PlannedKind.message,
      PlannedKind.attention,
    ]);
    for (final note in h.shown) {
      expect(note.body, h.l10n.t('newMessage'));
      expect(note.lines.single.who, isNull);
    }
    expect(h.shown.first.title, 'Desk');
    expect(h.shown.first.groupConversation, isTrue);

    h.preview = true;
    h.shown.clear();
    h.answer = (path) => path == '/threads/inbox'
        ? [
            inboxJson(
              't-desk',
              groupId: 'g-desk',
              unread: 2,
              last: lastMessage(
                id: 'm9',
                seq: 9,
                agentId: 'a-omar',
                content: 'Done.',
                at: t0.add(const Duration(minutes: 2)),
              ),
            ),
          ]
        : const [];
    await runBackgroundCheck(h.deps(now: t0.add(const Duration(minutes: 3))));
    expect(h.shown.single.body, 'Done.');
    expect(h.shown.single.lines.last.who, 'Omar');
  });

  test(
    "the device check reads the app's «Text preview» (on unless switched off)",
    () async {
      SharedPreferences.setMockInitialValues({});
      expect(await BackgroundCheckDeps.device().showPreview(), isTrue);
      SharedPreferences.setMockInitialValues({'lonora.notify.preview': false});
      expect(await BackgroundCheckDeps.device().showPreview(), isFalse);
    },
  );

  test('first run writes the baseline and announces nothing', () async {
    final h = Harness(stored: session)
      ..answer = (path) => path == '/threads/inbox'
          ? [inboxJson('t-sara', unread: 3, last: lastMessage(id: 'm', seq: 7))]
          : [attentionJson('a1')];
    expect(await runBackgroundCheck(h.deps()), BackgroundOutcome.baseline);
    expect(h.shown, isEmpty);
    expect(h.store.state!.seqs, {'t-sara': 7});
    expect(h.store.state!.seenAttention, ['a1']);
    expect(h.requests, unorderedEquals(['/threads/inbox', '/attention']));
  });

  test('a later run posts what changed and stores the next cursor', () async {
    final h = Harness(stored: session);
    h.store.state = PollState(
      ownerId: 'owner-1',
      server: server,
      since: t0.subtract(const Duration(minutes: 20)),
      seqs: const {'t-sara': 7},
      notifiedAttention: const {'gone'},
      titles: const {'t-sara': 'Sara'},
    );
    h.answer = (path) => path == '/threads/inbox'
        ? [
            inboxJson(
              't-sara',
              agentId: 'a-sara',
              unread: 1,
              last: lastMessage(id: 'm8', seq: 8, agentId: 'a-sara'),
            ),
          ]
        : [attentionJson('a2', threadId: 't-sara')];
    expect(
      await runBackgroundCheck(h.deps(now: t0.add(const Duration(minutes: 1)))),
      BackgroundOutcome.checked,
    );
    expect(h.shown.map((n) => n.kind), [
      PlannedKind.message,
      PlannedKind.attention,
    ]);
    expect(h.shown.first.title, 'Sara');
    expect(h.clearedAttention, ['gone']);
    expect(h.store.state!.seqs['t-sara'], 8);
    // Nothing twice.
    h.shown.clear();
    await runBackgroundCheck(h.deps(now: t0.add(const Duration(minutes: 20))));
    expect(h.shown, isEmpty);
  });

  test(
    '401 stops the schedule; other failures wait for the next period',
    () async {
      final h = Harness(stored: session)
        ..answer = (_) => const BackgroundHttpError(401);
      h.store.state = baselineState(
        ownerId: 'owner-1',
        server: server,
        inbox: const [],
        attention: const [],
        now: t0,
      );
      expect(
        await runBackgroundCheck(h.deps()),
        BackgroundOutcome.unauthorized,
      );
      expect(h.cancelled, 1);
      expect(h.store.state, isNull);

      final h2 = Harness(stored: session)
        ..answer = (_) => const BackgroundHttpError(503);
      expect(await runBackgroundCheck(h2.deps()), BackgroundOutcome.failed);
      expect(h2.cancelled, 0);
    },
  );

  test('the foreground baseline names conversations and keeps rules', () {
    final shell = demoShell(attention: [attentionJson('x')]);
    final app = AppState(
      session: const SessionState(
        status: SessionStatus.signedIn,
        server: server,
        owner: Owner(id: 'owner-1', email: 'o@example.com'),
      ),
      shell: shell,
      prefs: const PrefsState(locale: 'en'),
    );
    final snap = foregroundSnapshot(
      app,
      now: t0,
      foreground: true,
      rules: const DeliveryRules(off: {'a-omar'}),
    );
    expect(snap.titles, {'t-sara': 'Sara', 't-omar': 'Omar', 't-desk': 'Desk'});
    expect(snap.agentNames['a-sara'], 'Sara');
    expect(snap.seenAttention, ['x']);
    expect(snap.lang, 'en');
    expect(snap.off, {'a-omar'});
    expect(snap.foregroundAt, t0);
    expect(snap.toJson().toString(), isNot(contains('secret-token-value')));
    final away = foregroundSnapshot(app, now: t0, foreground: false);
    expect(away.foregroundAt, isNull);
  });

  test('conversations read in the app, or open, drop their notification lines', () {
    final shell = demoShell();
    final inbox = [
      InboxEntry.fromJson(inboxJson('t-sara', agentId: 'a-sara')),
      InboxEntry.fromJson(inboxJson('t-omar', agentId: 'a-omar', unread: 2)),
      InboxEntry.fromJson(inboxJson('t-desk', groupId: 'g-desk', unread: 1)),
    ];
    final app = AppState(
      session: const SessionState(
        status: SessionStatus.signedIn,
        server: server,
        owner: Owner(id: 'owner-1', email: 'o@example.com'),
      ),
      shell: shell.copyWith(inbox: inbox),
      openThreadId: 't-desk',
    );
    const line = [NoteLine('Earlier answer')];
    final snap = foregroundSnapshot(
      app,
      now: t0,
      foreground: true,
      previous: PollState(
        ownerId: 'owner-1',
        server: server,
        since: t0.subtract(const Duration(hours: 1)),
        notified: const {
          't-sara': line,
          't-omar': line,
          't-desk': line,
          't-gone': line,
        },
      ),
    );
    // t-sara was read (unread 0), t-desk is open, t-gone left the inbox.
    expect(snap.notified.keys, ['t-omar']);

    // The next background answer in t-sara is one line, not the old ones again.
    final result = computePoll(
      snap,
      inbox: [
        inboxJson(
          't-sara',
          agentId: 'a-sara',
          unread: 1,
          last: lastMessage(
            id: 'm9',
            seq: 99,
            agentId: 'a-sara',
            content: 'New answer',
            at: t0.add(const Duration(minutes: 5)),
          ),
        ),
      ],
      attention: const [],
      now: t0.add(const Duration(minutes: 6)),
      attentionText: (_, _) => '',
      newMessage: 'New message',
    );
    expect(result.notes.single.lines.map((l) => l.text), ['New answer']);
  });

  test(
    'a refused model names its failure family and provider from parameters',
    () async {
      final h = Harness(stored: session);
      h.store.state = PollState(
        ownerId: 'owner-1',
        server: server,
        since: t0.subtract(const Duration(minutes: 20)),
      );
      h.l10n.register({
        'attention.model.auth': [
          'رفض {provider} مفتاح النموذج',
          'Model key rejected by {provider}',
        ],
      });
      h.answer = (path) => path == '/threads/inbox'
          ? const []
          : [
              attentionJson(
                'm1',
                code: 'model_access_failed',
                parameters: const {'reason': 'auth', 'provider_name': 'Acme'},
              ),
            ];
      await runBackgroundCheck(h.deps(now: t0.add(const Duration(minutes: 1))));
      expect(h.shown.single.body, 'رفض Acme مفتاح النموذج');
    },
  );
}
