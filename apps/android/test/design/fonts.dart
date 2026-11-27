// Real fonts for widget/golden tests.
//
// flutter_test renders every glyph with the Ahem test font unless real fonts are registered. Call
// [loadAppFonts] once (e.g. in `setUpAll`) before pumping widgets whose goldens should show real text
// (Roboto, Android's default) and Lucide icons.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

bool _loaded = false;

/// Registers every font family declared in the app's FontManifest (Lucide from forui, MaterialIcons)
/// and the Flutter SDK's Roboto as `Roboto` (see `testFontFamily` in harness.dart), so text and icons
/// render with real glyphs.
///
/// Arabic: the test engine has no system fallback font, so when the Flutter SDK's
/// `NotoNaskhArabic-Regular.ttf` test font is available it is registered as the `NotoNaskhArabic`
/// family. Pass it as `fontFamilyFallback` (see `testFontFallback` in harness.dart) so Arabic strings
/// render with real shaping, the way Android's system fallback does on a device.
Future<void> loadAppFonts() async {
  if (_loaded) return;
  TestWidgetsFlutterBinding.ensureInitialized();

  final manifest = json.decode(
    await rootBundle.loadString('FontManifest.json'),
  ) as List<dynamic>;
  final arabic = _arabicFallback();
  for (final entry in manifest.cast<Map<String, dynamic>>()) {
    final family = entry['family'] as String;
    final loader = FontLoader(family);
    for (final font
        in (entry['fonts'] as List<dynamic>).cast<Map<String, dynamic>>()) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  if (arabic != null) {
    await (FontLoader('NotoNaskhArabic')..addFont(Future.value(arabic))).load();
  }
  final roboto = FontLoader('Roboto');
  for (final weight in ['Light', 'Regular', 'Medium', 'Bold', 'Black']) {
    final file = File(
      '$_flutterRoot/bin/cache/artifacts/material_fonts/Roboto-$weight.ttf',
    );
    if (file.existsSync()) {
      roboto.addFont(
        Future.value(ByteData.sublistView(file.readAsBytesSync())),
      );
    }
  }
  await roboto.load();
  _loaded = true;
}

String get _flutterRoot =>
    Platform.environment['FLUTTER_ROOT'] ?? '/opt/flutter';

ByteData? _arabicFallback() {
  final file = File(
    '$_flutterRoot/engine/src/flutter/txt/third_party/fonts/NotoNaskhArabic-Regular.ttf',
  );
  if (!file.existsSync()) return null;
  final bytes = file.readAsBytesSync();
  return ByteData.sublistView(Uint8List.fromList(bytes));
}
