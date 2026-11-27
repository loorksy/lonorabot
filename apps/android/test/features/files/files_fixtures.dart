// Files fixtures: artifact records in the server's shape and small real file bodies (a PNG
// encoded here, Markdown, CSV, JSON, code, HTML, text).
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:lonora/core/json.dart';

import '../market/wpf_harness.dart';

Json artifact(
  String id,
  String name,
  String mediaType,
  int size, {
  String? thread = 't-gold',
  String? agent,
  String created = '2026-11-26T10:00:00Z',
  int version = 1,
}) => {
  'id': id,
  'agent_id': agent,
  'thread_id': thread,
  'kind': 'artifacts',
  'version': version,
  'payload': {
    'name': name,
    'key': '$id/$name',
    'size': size,
    'media_type': mediaType,
    'sha256': 'x',
  },
  'state': {},
  'created_at': created,
  'updated_at': created,
};

const markdownBody = '''# تقرير الذهب الأسبوعي

اختبر **XAUUSD** مستوى 2395 مرتين هذا الأسبوع.

- الدعم: 2371
- المقاومة: 2405

> السيناريو الأساسي: تداول عرضي حتى بيانات الوظائف.
''';

const csvBody = '''time,open,high,low,close
2026-11-25 10:00,2380.10,2384.60,2377.90,2383.20
2026-11-25 11:00,2383.20,2391.00,2382.40,2390.70
2026-11-25 12:00,2390.70,2392.80,2386.80,2388.80
"2026-11-25 13:00",2388.80,2395.10,2388.00,2394.60
''';

const jsonBody =
    '{"symbol":"XAUUSD","levels":{"support":[2371,2360],"resistance":[2405]},"bias":"neutral"}';

const pythonBody = '''def ema(values, period):
    k = 2 / (period + 1)
    out = []
    for v in values:
        out.append(v if not out else v * k + out[-1] * (1 - k))
    return out
''';

const htmlBody =
    '<html><body><h1>Report</h1><script>alert(1)</script></body></html>';

const textBody = 'ملاحظات الاجتماع:\nمراجعة حدود المخاطرة يوم الأحد.\n';

int _crc(List<int> bytes) {
  var c = 0xFFFFFFFF;
  for (final b in bytes) {
    c ^= b;
    for (var k = 0; k < 8; k++) {
      c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
    }
  }
  return c ^ 0xFFFFFFFF;
}

List<int> _chunk(String type, List<int> data) {
  final body = [...ascii.encode(type), ...data];
  final len = ByteData(4)..setUint32(0, data.length);
  final crc = ByteData(4)..setUint32(0, _crc(body));
  return [...len.buffer.asUint8List(), ...body, ...crc.buffer.asUint8List()];
}

/// A [w] × [h] RGB PNG: a sky-to-sea gradient with a sun disc (Lonora-drawn test art).
Uint8List gradientPng(int w, int h) {
  final raw = <int>[];
  for (var y = 0; y < h; y++) {
    raw.add(0);
    for (var x = 0; x < w; x++) {
      final t = y / h;
      final dx = x - w * 0.7, dy = y - h * 0.35;
      final sun = dx * dx + dy * dy < (h * 0.12) * (h * 0.12);
      if (sun) {
        raw.addAll([255, 196, 72]);
      } else if (t < 0.6) {
        raw.addAll([(90 + 120 * t).round(), (150 + 80 * t).round(), 235]);
      } else {
        raw.addAll([
          20,
          (90 + 60 * (1 - t)).round(),
          (150 + 40 * (1 - t)).round(),
        ]);
      }
    }
  }
  final ihdr = ByteData(13)
    ..setUint32(0, w)
    ..setUint32(4, h)
    ..setUint8(8, 8)
    ..setUint8(9, 2)
    ..setUint8(10, 0)
    ..setUint8(11, 0)
    ..setUint8(12, 0);
  return Uint8List.fromList([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, //
    ..._chunk('IHDR', ihdr.buffer.asUint8List()),
    ..._chunk('IDAT', ZLibCodec().encode(raw)),
    ..._chunk('IEND', const []),
  ]);
}

final png = gradientPng(240, 160);

final filesFixture = <Json>[
  artifact(
    'f-md',
    'تقرير الذهب.md',
    'text/markdown',
    utf8.encode(markdownBody).length,
    agent: 'a-gold',
    created: '2026-11-27T08:00:00Z',
  ),
  artifact(
    'f-png',
    'chart-snapshot.png',
    'image/png',
    png.length,
    agent: 'a-gold',
    created: '2026-11-27T07:30:00Z',
  ),
  artifact(
    'f-csv',
    'candles.csv',
    'text/csv',
    utf8.encode(csvBody).length,
    thread: 't-research',
    agent: 'a-research',
    created: '2026-11-26T18:00:00Z',
  ),
  artifact(
    'f-json',
    'levels.json',
    'application/json',
    jsonBody.length,
    created: '2026-11-26T12:00:00Z',
  ),
  artifact(
    'f-py',
    'ema.py',
    'text/x-python',
    pythonBody.length,
    thread: 't-research',
    created: '2026-11-25T09:00:00Z',
  ),
  artifact(
    'f-pdf',
    'statement-oct.pdf',
    'application/pdf',
    248311,
    thread: null,
    created: '2026-11-20T09:00:00Z',
  ),
  artifact(
    'f-html',
    'report.html',
    'text/html',
    htmlBody.length,
    thread: 't-research',
    created: '2026-11-19T09:00:00Z',
  ),
  artifact(
    'f-txt',
    'ملاحظات.txt',
    'text/plain',
    utf8.encode(textBody).length,
    created: '2026-11-18T09:00:00Z',
    version: 3,
  ),
];

void scriptFiles() {
  fakeApi.on('GET /artifacts', (_, _) => filesFixture);
  for (final f in filesFixture) {
    final id = f['id']! as String;
    fakeApi.on('GET /artifacts/$id', (_, _) => f);
  }
  fakeApi.files
    ..['/artifacts/f-md/file'] = Uint8List.fromList(utf8.encode(markdownBody))
    ..['/artifacts/f-png/file'] = png
    ..['/artifacts/f-csv/file'] = Uint8List.fromList(utf8.encode(csvBody))
    ..['/artifacts/f-json/file'] = Uint8List.fromList(utf8.encode(jsonBody))
    ..['/artifacts/f-py/file'] = Uint8List.fromList(utf8.encode(pythonBody))
    ..['/artifacts/f-pdf/file'] = Uint8List.fromList([0x25, 0x50, 0x44, 0x46])
    ..['/artifacts/f-html/file'] = Uint8List.fromList(utf8.encode(htmlBody))
    ..['/artifacts/f-txt/file'] = Uint8List.fromList(utf8.encode(textBody));
}

/// The inbox rows that tie conversations to agents.
final filesInbox = <Json>[
  {'thread_id': 't-gold', 'agent_id': 'a-gold'},
  {'thread_id': 't-research', 'agent_id': 'a-research'},
];

/// A scratch directory for files the screens write (share, open elsewhere).
Directory scratch() => Directory.systemTemp.createTempSync('wpf-files');
