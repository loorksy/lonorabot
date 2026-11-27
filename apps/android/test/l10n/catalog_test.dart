// The generated catalogs against their TS sources: same keys in both languages, the source
// counts, and up to date with the sources (re-run tool/i18n/port_i18n.mjs when this fails).
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, String> catalog(String lang) =>
    (jsonDecode(File('assets/l10n/$lang.json').readAsStringSync()) as Map)
        .cast<String, String>();

final Map<String, dynamic> manifest = jsonDecode(
  File('test/l10n/fixtures/catalog_manifest.json').readAsStringSync(),
) as Map<String, dynamic>;

/// The monorepo root, when the TS sources are next to this app.
final String repo = '../..';
File source(String path) => File('$repo/$path');
final bool haveSources = source('apps/mobile/lib/i18n.ts').existsSync();

/// The keys of a `name = { key: [...] }` table, as the inventory counts them.
List<String> tupleKeys(String path) => RegExp(
  r'^ {2}(\w+): \[',
  multiLine: true,
).allMatches(source(path).readAsStringSync()).map((m) => m[1]!).toList();

void main() {
  final ar = catalog('ar');
  final en = catalog('en');

  test('every key is in both catalogs, in the same order', () {
    expect(ar.keys.toList(), en.keys.toList());
  });

  test('key counts per catalog equal the source counts', () {
    final sources = (manifest['sources'] as Map).cast<String, dynamic>();
    int count(String path) => (sources[path] as Map)['keys'] as int;
    expect(count('apps/mobile/lib/i18n.ts'), 590);
    expect(count('apps/mobile/lib/labels-shell.ts'), 176);
    expect(count('apps/mobile/lib/labels-shell-extra.ts'), 2);
    expect(count('apps/mobile/lib/incoming-call-labels.json'), 16);
    expect(count('apps/mobile/lib/attention-labels.ts'), 27 + 4);

    for (final lang in [ar, en]) {
      final keys = lang.keys;
      expect(keys.length, manifest['total']);
      expect(keys.length, 590 + 176 + 2 + 16 + 31);
      expect(keys.where((k) => k.startsWith('sh_')).length, 176 + 2);
      expect(keys.where((k) => k.startsWith('incoming.')).length, 16);
      expect(keys.where((k) => k.startsWith('attention.')).length, 31);
      expect(
        keys.where((k) => !k.contains('.') && !k.startsWith('sh_')).length,
        590,
      );
    }
  });

  test('the keys are the sources\' own keys', () {
    if (!haveSources) return markTestSkipped('TS sources not checked out');
    final own = tupleKeys('apps/mobile/lib/i18n.ts');
    final shell = tupleKeys('apps/mobile/lib/labels-shell.ts');
    final extra = tupleKeys('apps/mobile/lib/labels-shell-extra.ts');
    expect(own.length, 590);
    expect(shell.length, 176);
    expect(extra.length, 2);
    final incoming = (jsonDecode(
      source('apps/mobile/lib/incoming-call-labels.json').readAsStringSync(),
    ) as Map).cast<String, dynamic>();
    final attention = (manifest['attention'] as Map).keys;
    final model = (manifest['attentionModel'] as Map).keys;
    expect(attention.length, 27);
    expect(model.length, 4);
    expect(en.keys.toList(), [
      ...own,
      ...shell,
      ...extra,
      for (final key in (incoming['en'] as Map).keys) 'incoming.$key',
      for (final code in attention) 'attention.$code',
      for (final reason in model) 'attention.model.$reason',
    ]);
    expect((incoming['ar'] as Map).keys, (incoming['en'] as Map).keys);
    for (final key in (incoming['en'] as Map).keys) {
      expect(en['incoming.$key'], (incoming['en'] as Map)[key]);
      expect(ar['incoming.$key'], (incoming['ar'] as Map)[key]);
    }
  });

  test('catalogs and core tables are up to date with the TS sources', () {
    if (!haveSources) return markTestSkipped('TS sources not checked out');
    final hashes = <String, String>{
      for (final entry in (manifest['sources'] as Map).entries)
        entry.key as String: (entry.value as Map)['sha256'] as String,
      ...(manifest['core'] as Map).cast<String, String>(),
    };
    for (final MapEntry(key: path, value: hash) in hashes.entries) {
      final now = sha256.convert(source(path).readAsBytesSync()).toString();
      expect(
        now,
        hash,
        reason: '$path changed: run node tool/i18n/port_i18n.mjs',
      );
    }
  });

  test('no empty text, and both languages have the same placeholders', () {
    final placeholder = RegExp(r'\{\w+\}');
    Set<String> of(String text) =>
        placeholder.allMatches(text).map((m) => m[0]!).toSet();
    for (final key in en.keys) {
      expect(en[key]!.trim(), isNotEmpty, reason: key);
      expect(ar[key]!.trim(), isNotEmpty, reason: key);
      expect(of(ar[key]!), of(en[key]!), reason: key);
    }
  });

  test('attention.<code> is the label attention-labels.ts names', () {
    final labels = (manifest['attention'] as Map).cast<String, String>();
    for (final MapEntry(key: code, value: label) in labels.entries) {
      expect(en['attention.$code'], en[label], reason: code);
      expect(ar['attention.$code'], ar[label], reason: code);
    }
    final model = (manifest['attentionModel'] as Map).cast<String, String>();
    for (final MapEntry(key: reason, value: label) in model.entries) {
      expect(en['attention.model.$reason'], en[label], reason: reason);
      expect(ar['attention.model.$reason'], ar[label], reason: reason);
    }
  });
}
