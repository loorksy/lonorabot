// Lonora's Markdown dialect: block structure, inline styles, link safety, streaming stability,
// and reading direction per block.
import 'package:flutter/widgets.dart' show TextDirection;
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/features/rich/markdown_parse.dart';
import 'package:lonora/l10n/l10n.dart';

T only<T>(List<MdBlock> blocks) {
  expect(blocks, hasLength(1));
  return blocks.single as T;
}

void main() {
  group('blocks', () {
    test('headings, paragraphs and line breaks', () {
      final blocks = parseMarkdown('# Title\n\nfirst line\nsecond line');
      expect(blocks, hasLength(2));
      final h = blocks[0] as MdHeading;
      expect(h.level, 1);
      expect(inlineText(h.inlines), 'Title');
      // A single newline is a line break, as web md() and Expo draw it.
      expect(
        inlineText((blocks[1] as MdParagraph).inlines),
        'first line\nsecond line',
      );
    });

    test('nested, ordered and task lists', () {
      final list = only<MdList>(parseMarkdown('3. three\n4. four\n   - inner'));
      expect(list.ordered, isTrue);
      expect(list.start, 3);
      expect(list.items, hasLength(2));
      expect(list.items[1].blocks.whereType<MdList>(), hasLength(1));

      final tasks = only<MdList>(
        parseMarkdown('- [x] done\n- [ ] todo\n- plain'),
      );
      expect(tasks.items.map((i) => i.checked), [true, false, null]);
      expect(blockText(tasks.items[0].blocks.first), 'done');
    });

    test('fenced code keeps its language and text', () {
      final code = only<MdCode>(
        parseMarkdown('```python\nprint("hi")\n  x = 1\n```'),
      );
      expect(code.language, 'python');
      expect(code.code, 'print("hi")\n  x = 1');
      expect(code.open, isFalse);
    });

    test('tables with alignment, quotes and rules', () {
      final blocks = parseMarkdown(
        '| Name | Qty |\n| :-- | --: |\n| Gold | 2 |\n| Silver | 10 |\n\n> quoted\n> more\n\n---',
      );
      final table = blocks[0] as MdTable;
      expect(table.header.map(inlineText), ['Name', 'Qty']);
      expect(table.align, [MdAlign.start, MdAlign.end]);
      expect(table.rows, hasLength(2));
      expect(inlineText(table.rows[1][0]), 'Silver');
      expect(blocks[1], isA<MdQuote>());
      expect(blocks[2], isA<MdRule>());
    });

    test('HTML is never interpreted', () {
      final p = only<MdParagraph>(
        parseMarkdown('a <b>bold</b> <script>x</script>'),
      );
      expect(inlineText(p.inlines), contains('<b>bold</b>'));
      expect(p.inlines.whereType<MdText>().every((t) => t.style == 0), isTrue);
    });
  });

  group('inline', () {
    test('bold, italic, strike, code and links', () {
      final p = only<MdParagraph>(
        parseMarkdown('**b** _i_ ~~s~~ `c` [site](https://example.com)'),
      );
      final runs = p.inlines.whereType<MdText>().toList();
      MdText run(String text) => runs.firstWhere((r) => r.text == text);
      expect(run('b').has(MdStyle.bold), isTrue);
      expect(run('i').has(MdStyle.italic), isTrue);
      expect(run('s').has(MdStyle.strike), isTrue);
      expect(run('c').has(MdStyle.code), isTrue);
      expect(run('site').href, 'https://example.com');
    });

    test('bare URLs link; unsafe schemes never do', () {
      final p = only<MdParagraph>(
        parseMarkdown(
          'see https://lonora.ai/docs and [x](javascript:alert(1))',
        ),
      );
      final links = p.inlines.whereType<MdText>().where((r) => r.href != null);
      expect(links.map((r) => r.href), ['https://lonora.ai/docs']);
    });

    test(
      'sanitizeLink keeps http(s), mailto, tel, lonora and relative links',
      () {
        expect(sanitizeLink('https://a.b'), 'https://a.b');
        expect(sanitizeLink('mailto:a@b.c'), 'mailto:a@b.c');
        expect(sanitizeLink('lonora://thread/1'), 'lonora://thread/1');
        expect(sanitizeLink('/charts?symbol=XAUUSD'), '/charts?symbol=XAUUSD');
        expect(sanitizeLink('javascript:alert(1)'), isNull);
        expect(sanitizeLink('data:text/html,x'), isNull);
        expect(sanitizeLink('file:///etc/passwd'), isNull);
      },
    );

    test('signed numbers are found for left-to-right isolation', () {
      final m = signedNumber.allMatches('الربح (+\$239) و -1.5% ثم 3-4');
      expect(m.map((x) => x[2]), [r'+$239', '-1.5%']);
    });

    test('artifact image sources', () {
      const id = '0f8fad5b-d9cb-469f-a165-70867728950e';
      expect(artifactIdOf('lonora://artifact/$id'), id);
      expect(artifactIdOf('/files/$id'), id);
      expect(artifactIdOf('/api/artifacts/$id/file?preview=true'), id);
      expect(artifactIdOf(id), id);
      expect(artifactIdOf('https://evil.example/$id.png'), isNull);
    });
  });

  group('streaming', () {
    test('an unterminated fence is closed and drawn as open code', () {
      final (closed, open) = closeUnterminatedFence('text\n```dart\nvoid main');
      expect(open, isTrue);
      expect(closed.endsWith('\n```'), isTrue);
      final blocks = parseMarkdown(
        'text\n\n```dart\nvoid main',
        streaming: true,
      );
      final code = blocks.last as MdCode;
      expect(code.open, isTrue);
      expect(code.code, 'void main');
      expect(code.language, 'dart');
    });

    test('the stable prefix ends at the last blank line outside a fence', () {
      const text = 'one\n\ntwo\n\n```\na\n\nb';
      final split = stableSplit(text);
      expect(text.substring(0, split), 'one\n\ntwo\n\n');
      expect(stableSplit('no blank line yet'), 0);
    });

    test('streaming and final parses agree on finished text', () {
      const text =
          '# Plan\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```js\nx()\n```\n\nDone.';
      final streamed = parseMarkdown(text, streaming: true);
      final whole = parseMarkdown(text);
      expect(streamed.map(blockText), whole.map(blockText));
      expect(
        streamed.map((b) => b.runtimeType),
        whole.map((b) => b.runtimeType),
      );
    });

    test('growing text keeps earlier blocks identical (cached prefix)', () {
      const head = 'first paragraph\n\nsecond paragraph\n\n';
      final a = parseMarkdown('${head}third', streaming: true);
      final b = parseMarkdown('${head}third and more', streaming: true);
      expect(identical(a.first, b.first), isTrue);
      expect(blockText(b.last), 'third and more');
    });
  });

  group('reading direction', () {
    test(
      'per block: Arabic letters read right to left, Latin left to right',
      () {
        final blocks = parseMarkdown('مرحبا بك\n\nHello there\n\n12345');
        final dirs = blocks.map((b) => readingDirection(blockText(b))).toList();
        expect(dirs, [TextDirection.rtl, TextDirection.ltr, null]);
        // A block without letters takes the message's direction.
        expect(
          textDirectionFor(blockText(blocks[2]), TextDirection.rtl),
          TextDirection.rtl,
        );
      },
    );
  });
}
