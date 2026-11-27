// Files: kinds and helpers, the library (list / grid, search, type, agent and conversation
// filters, menu: share, save, open elsewhere, delete, upload, new text file), the viewer by kind
// (Markdown, JSON, CSV, code, HTML as source, text, image, PDF → elsewhere), text edits with the
// expected version, and the zoomable image viewer; goldens.
//
// Regenerate goldens with: flutter test --update-goldens test/features/files

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderParagraph;
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/design/design.dart' show CircleIconButton, LnIcons;
import 'package:lonora/features/files/artifact_screen.dart';
import 'package:lonora/features/files/artifacts_screen.dart';
import 'package:lonora/features/files/file_name_title.dart';
import 'package:lonora/features/files/file_ops.dart';
import 'package:lonora/features/files/files_data.dart';
import 'package:lonora/features/files/image_viewer_screen.dart';
import 'package:lonora/features/rich/markdown_view.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:photo_view/photo_view.dart';

import '../../design/harness.dart' show lnTestApp, testFontFamily;
import '../market/wpf_harness.dart';
import 'files_fixtures.dart';

final shared = <(String, String)>[];
final saved = <(String, int)>[];
final opened = <String>[];
PickedFile? nextPick;

void fakeHandoffs() {
  shared.clear();
  saved.clear();
  opened.clear();
  FileHandoff.share = (path, mime, name) async => shared.add((name, mime));
  FileHandoff.save = (name, bytes, mime) async {
    saved.add((name, bytes.length));
    return Uri.parse('content://downloads/$name');
  };
  FileHandoff.open = (path, mime) async {
    opened.add(mime);
    return true;
  };
  FileHandoff.pick = () async => nextPick;
}

/// Whether an image on screen has its decoded pixels.
bool imageDecoded(WidgetTester tester) => tester
    .widgetList<RawImage>(find.byType(RawImage))
    .any((i) => i.image != null);

void main() {
  setUpAll(() async {
    await setUpWpf();
    final dir = scratch();
    cacheDirectory = () async => dir;
  });
  setUp(() async {
    await resetWpf();
    FileBytes.clear();
    fakeHandoffs();
  });
  tearDown(FileHandoff.reset);

  group('helpers', () {
    test('a long file name is cut in the middle, keeping its extension', () {
      // Ten units a character.
      double width(String text) => text.length * 10.0;
      expect(middleEllipsis('short.pdf', 200, width), 'short.pdf');
      expect(
        middleEllipsis('statement-october-2026.pdf', 120, width),
        'stateme….pdf',
      );
      // No extension (or one too long to be one): only the end is cut.
      expect(middleEllipsis('a-very-long-name', 80, width), 'a-very-…');
    });

    test('kinds by type and name', () {
      expect(fileKindOf('image/png', 'a.png'), FileKind.image);
      expect(fileKindOf('application/pdf', 'a'), FileKind.pdf);
      expect(fileKindOf('application/octet-stream', 'x.pdf'), FileKind.pdf);
      expect(fileKindOf('text/plain', 'notes.md'), FileKind.markdown);
      expect(fileKindOf('application/json', 'a'), FileKind.json);
      expect(fileKindOf('text/plain', 'a.csv'), FileKind.csv);
      expect(fileKindOf('text/x-python', 'ema.py'), FileKind.code);
      expect(fileKindOf('text/html', 'r.html'), FileKind.html);
      expect(fileKindOf('text/plain', 'a.txt'), FileKind.text);
      expect(fileKindOf('application/zip', 'a.zip'), FileKind.other);
      expect(fileKindOf('image/svg+xml', 'a.svg'), FileKind.other);
      expect(isTextKind(FileKind.code), isTrue);
      expect(isTextKind(FileKind.pdf), isFalse);
      expect(codeLanguage('a.MQ5'), 'cpp');
      expect(matchesFilter(FileKind.csv, FileFilter.data), isTrue);
      expect(matchesFilter(FileKind.pdf, FileFilter.documents), isTrue);
    });

    test('badges, csv, json, preview, cache names', () {
      expect(mimeBadge('application/pdf'), 'PDF');
      expect(mimeBadge('image/svg+xml'), 'SVG');
      expect(mimeBadge('application/x-ndjson; charset=utf-8'), 'NDJSON');
      final rows = parseCsv(csvBody);
      expect(rows, hasLength(5));
      expect(rows.first, ['time', 'open', 'high', 'low', 'close']);
      expect(rows.last.first, '2026-11-25 13:00');
      expect(parseCsv('a,"b ""q"", c"\r\n1,2'), [
        ['a', 'b "q", c'],
        ['1', '2'],
      ]);
      expect(parseCsv('a\nb\nc', maxRows: 2), hasLength(2));
      expect(prettyJson('{"a":1}'), '{\n  "a": 1\n}');
      expect(prettyJson('not json'), 'not json');
      final big = Uint8List(textPreviewBytes + 10)
        ..fillRange(0, textPreviewBytes + 10, 65);
      final p = previewText(big);
      expect(p.truncated, isTrue);
      expect(p.text.length, textPreviewBytes);
      expect(cacheName('../../etc/passwd'), '.._.._etc_passwd');
      expect(cacheName('تقرير الذهب.md'), 'تقرير_الذهب.md');
      expect(cacheName(''), 'artifact');
    });
  });

  group('library', () {
    testWidgets('lists files with type, size, agent and date', (tester) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ArtifactsScreen(),
        locale: 'en',
        store: wpfStore(locale: 'en', inbox: filesInbox),
      );
      expect(find.text('Artifacts'), findsOneWidget);
      expect(find.text('تقرير الذهب.md'), findsOneWidget);
      // Q11: the dot holds to the part before it.
      expect(find.textContaining('MARKDOWN$dotSeparator'), findsOneWidget);
      expect(find.textContaining('Gold desk'), findsWidgets);
      await tapAndSettle(tester, find.text('Images'));
      expect(find.text('chart-snapshot.png'), findsOneWidget);
      expect(find.text('candles.csv'), findsNothing);
      await tapAndSettle(tester, find.text('All'));
      await tester.enterText(find.byType(TextField), 'csv');
      await tester.pumpAndSettle();
      expect(find.text('candles.csv'), findsOneWidget);
      expect(find.text('ema.py'), findsNothing);
      await tester.enterText(find.byType(TextField), 'zzz');
      await tester.pumpAndSettle();
      expect(find.text('No results'), findsOneWidget);
      await unmount(tester);
    });

    testWidgets('filters by the conversation and by agent', (tester) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ArtifactsScreen(threadId: 't-research'),
        locale: 'en',
        store: wpfStore(locale: 'en', inbox: filesInbox),
      );
      expect(find.text('candles.csv'), findsOneWidget);
      expect(find.text('ema.py'), findsOneWidget);
      expect(find.text('chart-snapshot.png'), findsNothing);
      await tapAndSettle(tester, find.textContaining('This conversation'));
      expect(find.text('chart-snapshot.png'), findsOneWidget);
      await tapAndSettle(tester, find.text('Gold desk'));
      expect(find.text('chart-snapshot.png'), findsOneWidget);
      expect(find.text('candles.csv'), findsNothing);
      await unmount(tester);
    });

    testWidgets('the search survives switching list and grid', (tester) async {
      scriptFiles();
      await pumpWpf(tester, const ArtifactsScreen(), locale: 'en');
      await tester.enterText(find.byType(TextField), 'csv');
      await tester.pumpAndSettle();
      expect(find.text('candles.csv'), findsOneWidget);
      expect(find.text('ema.py'), findsNothing);
      String search() =>
          tester.widget<TextField>(find.byType(TextField)).controller!.text;
      // The grid builds a new field in another subtree: it shows the same search.
      await tapAndSettle(tester, find.bySemanticsLabel('Grid view'));
      expect(search(), 'csv');
      expect(find.byType(FileTile), findsOneWidget);
      // wf:C6: the list glyph turns with the reading direction (its bullets at the start).
      expect(find.byIcon(LnIcons.list), findsOneWidget);
      expect(LnIcons.list.matchTextDirection, isTrue);
      await tapAndSettle(tester, find.bySemanticsLabel('List view'));
      expect(search(), 'csv');
      expect(find.byType(FileRow), findsOneWidget);
      await unmount(tester);
    });

    testWidgets('a conversation reads its own files; empty, it offers upload', (
      tester,
    ) async {
      fakeApi.on(
        'GET /artifacts',
        (_, q) => q?['thread_id'] == null ? filesFixture : const <Object>[],
      );
      await pumpWpf(
        tester,
        const ArtifactsScreen(threadId: 't-empty'),
        locale: 'en',
      );
      expect(
        [for (final c in fakeApi.callsTo('GET', '/artifacts')) c.query],
        containsAll([
          null,
          {'thread_id': 't-empty'},
        ]),
      );
      // The conversation scope is no search: the empty library message and its upload.
      expect(
        find.text(
          'No files yet. Conversation attachments and agent files appear here.',
        ),
        findsOneWidget,
      );
      expect(find.text('Upload a file'), findsOneWidget);
      await unmount(tester);
    });

    testWidgets('an older conversation file comes from its own read', (
      tester,
    ) async {
      fakeApi.on(
        'GET /artifacts',
        (_, q) => q?['thread_id'] == null
            ? filesFixture
            : [
                artifact(
                  'f-old',
                  'archive.txt',
                  'text/plain',
                  10,
                  thread: 't-old',
                  created: '2025-01-01T00:00:00Z',
                ),
              ],
      );
      await pumpWpf(
        tester,
        const ArtifactsScreen(threadId: 't-old'),
        locale: 'en',
      );
      expect(find.text('archive.txt'), findsOneWidget);
      await unmount(tester);
    });

    testWidgets('menu: share, save, open elsewhere, delete confirmed', (
      tester,
    ) async {
      scriptFiles();
      fakeApi.on('DELETE /artifacts/f-json', (_, _) => {'deleted': true});
      await pumpWpf(tester, const ArtifactsScreen(), locale: 'en');
      Future<void> menu(String name) => tapAndSettle(
        tester,
        find.descendant(
          of: find.ancestor(
            of: find.text(name),
            matching: find.byType(FileRow),
          ),
          matching: find.bySemanticsLabel('More'),
        ),
      );
      await menu('levels.json');
      await tapAndSettle(tester, find.text('Share'));
      await settleIo(tester, until: () => shared.isNotEmpty);
      expect(shared.single, ('levels.json', 'application/json'));
      await menu('levels.json');
      await tapAndSettle(tester, find.text('Download'));
      expect(saved.single, ('levels.json', jsonBody.length));
      await settleToasts(tester);
      await menu('levels.json');
      await tapAndSettle(tester, find.text('Open in another app'));
      await settleIo(tester, until: () => opened.isNotEmpty);
      expect(opened.single, 'application/json');
      await menu('levels.json');
      await tapAndSettle(tester, find.text('Delete'));
      expect(find.text('Delete this file?'), findsOneWidget);
      await tapAndSettle(tester, find.text('Delete').last);
      expect(fakeApi.callsTo('DELETE', '/artifacts/f-json'), hasLength(1));
      expect(find.text('levels.json'), findsNothing);
      await settleToasts(tester);
      await unmount(tester);
    });

    testWidgets('upload and new text file go to the conversation', (
      tester,
    ) async {
      scriptFiles();
      nextPick = (path: '/tmp/x.pdf', name: 'contract.pdf', mimeType: null);
      fakeApi.on(
        'UPLOAD /artifacts/upload',
        (body, _) => artifact(
          'f-new',
          (body! as Map)['file'] as String,
          'application/pdf',
          10,
          thread: 't-gold',
        ),
      );
      await pumpWpf(
        tester,
        const ArtifactsScreen(threadId: 't-gold'),
        locale: 'en',
      );
      await tapAndSettle(tester, find.bySemanticsLabel('Add a file'));
      await tapAndSettle(tester, find.text('Upload a file'));
      expect(fakeApi.callsTo('UPLOAD', '/artifacts/upload').single.body, {
        'file': 'contract.pdf',
        'mime': null,
        'thread_id': 't-gold',
      });
      expect(find.text('contract.pdf'), findsOneWidget);
      await settleToasts(tester);
      await tapAndSettle(tester, find.bySemanticsLabel('Add a file'));
      await tapAndSettle(tester, find.text('New text file'));
      expect(find.text('note.txt'), findsOneWidget);
      await tester.enterText(find.byType(TextField).last, 'Buy the dip? No.');
      // The button spins while the new file is written: no settling until it is sent.
      await tester.tap(find.text('Save file'));
      await tester.pump();
      await settleIo(
        tester,
        until: () => find.byType(TextFileEditor).evaluate().isEmpty,
      );
      final upload = fakeApi.callsTo('UPLOAD', '/artifacts/upload').last.body;
      expect(upload, {
        'file': 'note.txt',
        'mime': 'text/plain',
        'thread_id': 't-gold',
      });
      await settleToasts(tester);
      await unmount(tester);
    });

    testWidgets('grid view and empty library', (tester) async {
      scriptFiles();
      await pumpWpf(tester, const ArtifactsScreen(), locale: 'en');
      await tapAndSettle(tester, find.bySemanticsLabel('Grid view'));
      expect(find.byType(FileTile), findsWidgets);
      await unmount(tester);
      fakeApi.on('GET /artifacts', (_, _) => []);
      await pumpWpf(tester, const ArtifactsScreen(), locale: 'en');
      expect(
        find.text(
          'No files yet. Conversation attachments and agent files appear here.',
        ),
        findsOneWidget,
      );
      await unmount(tester);
    });

    testWidgets('offline first load offers a retry', (tester) async {
      fakeApi.on('GET /artifacts', (_, _) => throw ApiError.network());
      await pumpWpf(tester, const ArtifactsScreen(), locale: 'en');
      expect(find.text('Retry'), findsOneWidget);
      scriptFiles();
      await tapAndSettle(tester, find.text('Retry'));
      expect(find.text('candles.csv'), findsOneWidget);
      await unmount(tester);
    });
  });

  group('viewer', () {
    testWidgets('markdown through the rich renderer', (tester) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ArtifactScreen(artifactId: 'f-md'),
        locale: 'en',
      );
      expect(find.byType(MarkdownView), findsOneWidget);
      expect(find.text('Open conversation'), findsOneWidget);
      await tapAndSettle(tester, find.text('Open conversation'));
      expect(shownRoute(tester), '/chats/thread/t-gold');
      await unmount(tester);
    });

    testWidgets('json is indented, csv is a table, html is source', (
      tester,
    ) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ArtifactScreen(artifactId: 'f-json'),
        locale: 'en',
      );
      expect(find.textContaining('"support": ['), findsOneWidget);
      await unmount(tester);
      await pumpWpf(
        tester,
        const ArtifactScreen(artifactId: 'f-csv'),
        locale: 'en',
      );
      expect(find.byType(CsvTable), findsOneWidget);
      expect(find.text('2394.60'), findsOneWidget);
      await unmount(tester);
      await pumpWpf(
        tester,
        const ArtifactScreen(artifactId: 'f-html'),
        locale: 'en',
      );
      expect(
        find.text(
          'HTML is shown as safe source here. Share the file to open it in a trusted app.',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('<script>'), findsOneWidget);
      await unmount(tester);
    });

    testWidgets('pdf opens in another app without a preview download', (
      tester,
    ) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ArtifactScreen(artifactId: 'f-pdf'),
        locale: 'en',
      );
      expect(fakeApi.calls.where((c) => c.method == 'BYTES'), isEmpty);
      expect(
        find.text(
          'Preview is unavailable for this file type. Download or share it to open.',
        ),
        findsOneWidget,
      );
      await tapAndSettle(tester, find.text('Open in another app'));
      await settleIo(tester, until: () => opened.isNotEmpty);
      expect(opened.single, 'application/pdf');
      await unmount(tester);
    });

    testWidgets('editing a text file sends its version', (tester) async {
      scriptFiles();
      fakeApi.on(
        'PUT /artifacts/f-txt/text',
        (body, _) =>
            artifact('f-txt', 'ملاحظات.txt', 'text/plain', 10, version: 4),
      );
      await pumpWpf(
        tester,
        const ArtifactScreen(artifactId: 'f-txt'),
        locale: 'en',
      );
      expect(find.textContaining('مراجعة حدود المخاطرة'), findsOneWidget);
      await tapAndSettle(tester, find.bySemanticsLabel('More'));
      await tapAndSettle(tester, find.text('Edit'));
      await tester.enterText(find.byType(TextField).last, 'محدث');
      await tapAndSettle(tester, find.text('Save file'));
      expect(fakeApi.callsTo('PUT', '/artifacts/f-txt/text').single.body, {
        'expected_version': 3,
        'name': 'ملاحظات.txt',
        'content': 'محدث',
      });
      await unmount(tester);
    });

    testWidgets('a version conflict is explained', (tester) async {
      scriptFiles();
      fakeApi.on(
        'PUT /artifacts/f-txt/text',
        (_, _) => throw ApiError(status: 409, code: 'version_conflict'),
      );
      await pumpWpf(
        tester,
        const ArtifactScreen(artifactId: 'f-txt'),
        locale: 'en',
      );
      await tapAndSettle(tester, find.bySemanticsLabel('More'));
      await tapAndSettle(tester, find.text('Edit'));
      await tapAndSettle(tester, find.text('Save file'));
      expect(
        find.text(L10n.instance.errorText('version_conflict')),
        findsOneWidget,
      );
      await settleToasts(tester);
      await unmount(tester);
    });

    testWidgets('image opens the zoomable viewer', (tester) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ArtifactScreen(artifactId: 'f-png'),
        locale: 'en',
        pages: {
          '/files/f-png/image': (_) =>
              const ImageViewerScreen(artifactId: 'f-png'),
        },
      );
      expect(find.byType(Image), findsWidgets);
      // The image is decoded for real before it has a size to tap.
      await settleIo(tester);
      await tapAndSettle(
        tester,
        find.bySemanticsLabel('Image: chart-snapshot.png'),
      );
      expect(find.byType(PhotoView), findsOneWidget);
      await tapAndSettle(tester, find.bySemanticsLabel('Save image'));
      expect(saved.single.$1, 'chart-snapshot.png');
      await settleToasts(tester);
      await unmount(tester);
    });

    testWidgets('the viewer title uses the free width and keeps the '
        'extension', (tester) async {
      scriptFiles();
      // The viewer's spinner runs until the image is decoded for real.
      await pumpWpf(
        tester,
        const ImageViewerScreen(artifactId: 'f-png'),
        settle: false,
      );
      await settleIo(tester, until: () => imageDecoded(tester));
      // «chart-snapshot.png» is wider than the centred room between two-circle insets: it
      // moves beside the circles, whole.
      final title = find.text('chart-snapshot.png');
      expect(title, findsOneWidget);
      expect(
        tester
            .renderObject<RenderParagraph>(
              find.descendant(of: title, matching: find.byType(RichText)),
            )
            .didExceedMaxLines,
        isFalse,
      );
      // The same gap to the back circle as to the nearer of the two others.
      final text = tester.getRect(title);
      final boxes = [
        for (var i = 0; i < 3; i++)
          tester.getRect(find.byType(CircleIconButton).at(i)),
      ];
      final before = boxes.where((b) => b.right <= text.left);
      final after = boxes.where((b) => b.left >= text.right);
      expect(before, isNotEmpty);
      expect(after, isNotEmpty);
      expect(
        text.left - before.map((b) => b.right).reduce(math.max),
        moreOrLessEquals(
          after.map((b) => b.left).reduce(math.min) - text.right,
          epsilon: 0.5,
        ),
      );
      await unmount(tester);
    });

    testWidgets('the file viewer title uses the free width and keeps the '
        'extension', (tester) async {
      scriptFiles();
      final handle = tester.ensureSemantics();
      await pumpWpf(tester, const ArtifactScreen(artifactId: 'f-pdf'));
      // Before: centred between two-circle insets on both sides, «statement-oct.…».
      final title = find.descendant(
        of: find.byType(FileNameTitle),
        matching: find.byType(Text),
      );
      expect(tester.widget<Text>(title).data, 'statement-oct.pdf');
      expect(
        tester
            .renderObject<RenderParagraph>(
              find.descendant(of: title, matching: find.byType(RichText)),
            )
            .didExceedMaxLines,
        isFalse,
      );
      // Still the page's header, read whole.
      expect(
        tester.getSemantics(find.bySemanticsLabel('statement-oct.pdf')),
        isSemantics(label: 'statement-oct.pdf', isHeader: true),
      );
      handle.dispose();
      await unmount(tester);
    });

    testWidgets('a file name too long for the header keeps its extension', (
      tester,
    ) async {
      const name = 'statement-october-2026-broker-account.pdf';
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        lnTestApp(
          child: const Align(
            alignment: Alignment.topCenter,
            child: SizedBox(
              width: 365,
              child: FileNameTitle(
                name: name,
                start: 56,
                end: 112,
                style: TextStyle(fontFamily: testFontFamily, fontSize: 17),
              ),
            ),
          ),
        ),
      );
      final text = tester.widget<Text>(find.byType(Text));
      expect(text.data, endsWith('….pdf'));
      expect(text.data!.length, lessThan(name.length));
      // Within the free width between the circles.
      expect(tester.getSize(find.byType(Text)).width, lessThanOrEqualTo(197));
      expect(find.bySemanticsLabel(name), findsOneWidget);
      handle.dispose();
    });

    testWidgets('the image viewer keeps light status bar icons', (
      tester,
    ) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ImageViewerScreen(artifactId: 'f-png'),
        settle: false,
      );
      expect(
        tester
            .widget<AnnotatedRegion<SystemUiOverlayStyle>>(
              find.byType(AnnotatedRegion<SystemUiOverlayStyle>).last,
            )
            .value,
        SystemUiOverlayStyle.light,
      );
      await unmount(tester);
    });

    testWidgets('a file name stops at 160 characters', (tester) async {
      scriptFiles();
      await pumpWpf(tester, const ArtifactsScreen(), locale: 'en');
      await tapAndSettle(tester, find.bySemanticsLabel('Add a file'));
      await tapAndSettle(tester, find.text('New text file'));
      await tester.enterText(
        find.byType(TextField).at(find.byType(TextField).evaluate().length - 2),
        'n' * 200,
      );
      await tester.pump();
      expect(
        tester
            .widget<TextField>(
              find
                  .descendant(
                    of: find.byType(TextFileEditor),
                    matching: find.byType(TextField),
                  )
                  .first,
            )
            .controller!
            .text,
        hasLength(160),
      );
      await unmount(tester);
    });

    testWidgets('viewer of a file that is not an image', (tester) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ImageViewerScreen(artifactId: 'f-csv'),
        locale: 'en',
      );
      expect(find.text('This file is not an image.'), findsOneWidget);
      await unmount(tester);
    });
  });

  testWidgets('text scale 1.3 does not overflow', (tester) async {
    scriptFiles();
    await pumpWpf(
      tester,
      const ArtifactsScreen(),
      textScale: 1.3,
      store: wpfStore(inbox: filesInbox),
    );
    expect(tester.takeException(), isNull);
    await tapAndSettle(tester, find.bySemanticsLabel('عرض شبكي'));
    expect(tester.takeException(), isNull);
    await unmount(tester);
    await pumpWpf(
      tester,
      const ArtifactScreen(artifactId: 'f-csv'),
      textScale: 1.3,
    );
    expect(tester.takeException(), isNull);
    await unmount(tester);
  });

  group('goldens', () {
    for (final v in goldenVariants) {
      testWidgets('library ${v.name}', (tester) async {
        scriptFiles();
        await withRealShadows(() async {
          await pumpWpf(
            tester,
            const ArtifactsScreen(),
            brightness: v.brightness,
            locale: v.locale,
            store: wpfStore(locale: v.locale, inbox: filesInbox),
          );
          // The thumbnail is decoded for real.
          await settleIo(tester);
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile('goldens/files_${v.name}.png'),
          );
        });
        await unmount(tester);
      });
    }

    testWidgets('grid ar', (tester) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ArtifactsScreen(threadId: 't-gold'),
        store: wpfStore(inbox: filesInbox),
      );
      await tapAndSettle(tester, find.textContaining('هذه المحادثة'));
      await tapAndSettle(tester, find.bySemanticsLabel('عرض شبكي'));
      await settleIo(tester);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/files_grid_ar.png'),
      );
      await unmount(tester);
    });

    for (final (id, name, theme, locale) in [
      ('f-md', 'markdown', Brightness.light, 'ar'),
      ('f-csv', 'csv', Brightness.dark, 'en'),
      ('f-json', 'json', Brightness.light, 'en'),
      ('f-pdf', 'pdf', Brightness.dark, 'ar'),
      ('f-txt', 'text', Brightness.light, 'ar'),
    ]) {
      testWidgets('viewer $name', (tester) async {
        scriptFiles();
        await pumpWpf(
          tester,
          ArtifactScreen(artifactId: id),
          brightness: theme,
          locale: locale,
          store: wpfStore(locale: locale, inbox: filesInbox),
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(
            'goldens/artifact_${name}_${theme.name}_$locale.png',
          ),
        );
        await unmount(tester);
      });
    }

    testWidgets('image viewer', (tester) async {
      scriptFiles();
      await pumpWpf(
        tester,
        const ImageViewerScreen(artifactId: 'f-png'),
        settle: false,
      );
      await settleIo(tester, until: () => imageDecoded(tester));
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/image_viewer_ar.png'),
      );
      await unmount(tester);
    });
  });
}
