// Startup registration of every feature's labels: no key is defined twice with different words
// (L10n.register asserts on that in debug), and each added key has both an Arabic and an English text.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/app_strings.dart';
import 'package:lonora/l10n/l10n.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('registerAllStrings adds every table without a conflict', () async {
    final l10n = await L10n.load();
    final before = l10n.keys.toSet();
    registerAllStrings();
    final added = l10n.keys.toSet().difference(before);
    expect(added, isNotEmpty);
    for (final key in added) {
      expect(l10n.translate(key, 'ar').trim(), isNotEmpty, reason: key);
      expect(l10n.translate(key, 'en').trim(), isNotEmpty, reason: key);
    }
    // A second call is a no-op.
    final count = l10n.keys.length;
    registerAllStrings();
    expect(l10n.keys.length, count);
    l10n.setLocale(const Locale('en'));
    expect(l10n.t('android_market'), 'Market');
  });
}
