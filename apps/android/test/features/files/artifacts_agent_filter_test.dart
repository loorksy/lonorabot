// The files library opened for one agent (`/files?agent=<id>`, the agent profile's Files row):
// it starts filtered to that agent's files, its one-to-one conversation's own files and the
// agent's own files are read too, uploads under the filter are the agent's (in its
// conversation when it has one) and stay in view, an agent without files shows the empty
// library with its upload, the agent's chip clears the filter, and Back from a page opened
// directly returns to the agent.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/design/design.dart' show LnChoiceChip;
import 'package:lonora/features/files/artifacts_screen.dart';
import 'package:lonora/features/files/file_ops.dart'
    show FileHandoff, TextFileEditor;
import 'package:lonora/features/files/files_data.dart';
import 'package:lonora/state/realtime.dart';

import '../../design/harness.dart' show setGoldenViewport;
import '../market/wpf_harness.dart';
import 'files_fixtures.dart';

bool chipSelected(WidgetTester tester, String label) => tester
    .widget<LnChoiceChip>(find.widgetWithText(LnChoiceChip, label))
    .selected;

/// An upload answered with the record the server would store.
void answerUploads() => fakeApi.on(
  'UPLOAD /artifacts/upload',
  (body, _) => artifact(
    'f-new',
    (body! as Map)['file'] as String,
    'application/pdf',
    10,
    thread: (body as Map)['thread_id'] as String?,
    agent: body['agent_id'] as String?,
  ),
);

void main() {
  setUpAll(() async {
    await setUpWpf();
    final dir = scratch();
    cacheDirectory = () async => dir;
  });
  setUp(() async {
    await resetWpf();
    FileBytes.clear();
  });
  tearDown(FileHandoff.reset);

  testWidgets('starts with the agent\'s files; its chip clears the filter', (
    tester,
  ) async {
    scriptFiles();
    await pumpWpf(
      tester,
      const ArtifactsScreen(agentId: 'a-research'),
      locale: 'en',
      store: wpfStore(locale: 'en', inbox: filesInbox),
    );
    // Its own file and the files of its conversation.
    expect(find.text('candles.csv'), findsOneWidget);
    expect(find.text('ema.py'), findsOneWidget);
    expect(find.text('chart-snapshot.png'), findsNothing);
    expect(find.text('statement-oct.pdf'), findsNothing);
    expect(chipSelected(tester, 'محلل الأبحاث'), isTrue);
    expect(chipSelected(tester, 'Gold desk'), isFalse);
    await tapAndSettle(tester, find.text('محلل الأبحاث'));
    expect(find.text('chart-snapshot.png'), findsOneWidget);
    expect(find.text('candles.csv'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('the agent\'s conversation and own files are read too: older '
      'files are there', (tester) async {
    fakeApi.on(
      'GET /artifacts',
      (_, q) => q?['thread_id'] != null
          ? [
              artifact(
                'f-old',
                'archive.txt',
                'text/plain',
                10,
                thread: 't-research',
                created: '2025-01-01T00:00:00Z',
              ),
            ]
          : q?['agent_id'] != null
          ? [
              artifact(
                'f-own',
                'notes-2024.md',
                'text/markdown',
                10,
                thread: null,
                agent: 'a-research',
                created: '2024-06-01T00:00:00Z',
              ),
            ]
          : filesFixture,
    );
    await pumpWpf(
      tester,
      const ArtifactsScreen(agentId: 'a-research'),
      locale: 'en',
      store: wpfStore(locale: 'en', inbox: filesInbox),
    );
    expect(
      [for (final c in fakeApi.callsTo('GET', '/artifacts')) c.query],
      containsAll([
        null,
        {'thread_id': 't-research'},
        {'agent_id': 'a-research'},
      ]),
    );
    expect(find.text('archive.txt'), findsOneWidget);
    expect(find.text('notes-2024.md'), findsOneWidget);
    expect(find.text('candles.csv'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('an upload under the agent is the agent\'s, in its conversation, '
      'and stays', (tester) async {
    scriptFiles();
    FileHandoff.pick = () async =>
        (path: '/tmp/x.pdf', name: 'contract.pdf', mimeType: null);
    answerUploads();
    await pumpWpf(
      tester,
      const ArtifactsScreen(agentId: 'a-research'),
      locale: 'en',
      store: wpfStore(locale: 'en', inbox: filesInbox),
    );
    await tapAndSettle(tester, find.bySemanticsLabel('Add a file'));
    await tapAndSettle(tester, find.text('Upload a file'));
    expect(fakeApi.callsTo('UPLOAD', '/artifacts/upload').single.body, {
      'file': 'contract.pdf',
      'mime': null,
      'thread_id': 't-research',
      'agent_id': 'a-research',
    });
    expect(find.text('contract.pdf'), findsOneWidget);
    expect(chipSelected(tester, 'محلل الأبحاث'), isTrue);
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets('an agent without a conversation: an upload and a new text file '
      'are the agent\'s and stay in view', (tester) async {
    scriptFiles();
    FileHandoff.pick = () async =>
        (path: '/tmp/x.pdf', name: 'contract.pdf', mimeType: null);
    answerUploads();
    await pumpWpf(
      tester,
      const ArtifactsScreen(agentId: 'a-lonora'),
      locale: 'en',
      store: wpfStore(locale: 'en', inbox: filesInbox),
    );
    await tapAndSettle(tester, find.bySemanticsLabel('Add a file'));
    // The menu's item (the empty library offers its own upload under it).
    await tapAndSettle(tester, find.text('Upload a file').last);
    expect(fakeApi.callsTo('UPLOAD', '/artifacts/upload').single.body, {
      'file': 'contract.pdf',
      'mime': null,
      'agent_id': 'a-lonora',
    });
    expect(find.text('contract.pdf'), findsOneWidget);
    expect(chipSelected(tester, 'Lonora'), isTrue);
    await settleToasts(tester);

    await tapAndSettle(tester, find.bySemanticsLabel('Add a file'));
    await tapAndSettle(tester, find.text('New text file'));
    // The button spins while the new file is written: no settling until it is sent.
    await tester.tap(find.text('Save file'));
    await tester.pump();
    await settleIo(
      tester,
      until: () => find.byType(TextFileEditor).evaluate().isEmpty,
    );
    expect(fakeApi.callsTo('UPLOAD', '/artifacts/upload').last.body, {
      'file': 'note.txt',
      'mime': 'text/plain',
      'agent_id': 'a-lonora',
    });
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets('with the agent filter cleared, an upload is the workspace\'s', (
    tester,
  ) async {
    scriptFiles();
    FileHandoff.pick = () async =>
        (path: '/tmp/x.pdf', name: 'contract.pdf', mimeType: null);
    answerUploads();
    await pumpWpf(
      tester,
      const ArtifactsScreen(agentId: 'a-research'),
      locale: 'en',
      store: wpfStore(locale: 'en', inbox: filesInbox),
    );
    await tapAndSettle(tester, find.text('محلل الأبحاث'));
    await tapAndSettle(tester, find.bySemanticsLabel('Add a file'));
    await tapAndSettle(tester, find.text('Upload a file'));
    expect(fakeApi.callsTo('UPLOAD', '/artifacts/upload').single.body, {
      'file': 'contract.pdf',
      'mime': null,
    });
    await settleToasts(tester);
    await unmount(tester);
  });

  testWidgets(
    'an agent without files shows the empty library; its chip clears it',
    (tester) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ArtifactsScreen(agentId: 'a-lonora'),
        locale: 'en',
        store: wpfStore(locale: 'en', inbox: filesInbox),
      );
      // The agent is the page's own scope, not a search the owner typed.
      expect(
        find.text(
          'No files yet. Conversation attachments and agent files appear here.',
        ),
        findsOneWidget,
      );
      expect(find.text('Upload a file'), findsOneWidget);
      expect(find.text('No results'), findsNothing);
      expect(chipSelected(tester, 'Lonora'), isTrue);
      await tapAndSettle(tester, find.text('Lonora'));
      expect(find.text('candles.csv'), findsOneWidget);
      await unmount(tester);
    },
  );

  testWidgets('Back from a directly opened agent library goes to the agent', (
    tester,
  ) async {
    scriptFiles();
    setGoldenViewport(tester);
    final store = wpfStore(locale: 'en', inbox: filesInbox);
    realtime = fakeRealtime = FakeRealtime(store);
    final router = GoRouter(
      initialLocation: '/files?agent=a-research',
      routes: [
        GoRoute(
          path: '/files',
          builder: (_, s) =>
              ArtifactsScreen(agentId: s.uri.queryParameters['agent']),
        ),
        GoRoute(path: '/agent/:id', builder: (_, s) => Text('route:${s.uri}')),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(wpfApp(store: store, router: router, locale: 'en'));
    await tester.pumpAndSettle();
    await tapAndSettle(tester, find.bySemanticsLabel('Back'));
    expect(shownRoute(tester), '/agent/a-research');
    await unmount(tester);
  });
}
