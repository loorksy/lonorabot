// A file added under an agent against a REAL disposable Lonora server: `POST /artifacts/upload`
// stores the `agent_id` form field, and `fetchArtifacts(agentId:)` merges
// `GET /artifacts?agent_id=`, so the file is in the agent's library even with no conversation.
// The file is deleted again; the shared test token is used, so no session is opened.
//
// Runs only when LONORA_TEST_CREDS points at {server_url, bearer_token} of a disposable test
// server (see docs/android/analysis/lonora-local-runtime.md). Never point it at production.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/features/files/files_data.dart';

void main() {
  final credsPath = Platform.environment['LONORA_TEST_CREDS'];
  final creds = credsPath != null && File(credsPath).existsSync()
      ? asJson(jsonDecode(File(credsPath).readAsStringSync()))
      : null;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    HttpOverrides.global = null; // real network for this test
    await sl.reset();
    final client = ApiClient(userAgent: 'Lonora-Android/test');
    if (creds != null) {
      client.configure(
        server: asStr(creds['server_url']),
        token: asStr(creds['bearer_token']),
      );
    }
    sl.registerSingleton<ApiClient>(client);
    final dir = Directory.systemTemp.createTempSync('lonora_files_backend');
    cacheDirectory = () async => dir;
  });

  test(
    'a text file created under an agent is the agent\'s and in its library',
    () async {
      final agentId = asStr(asJsonList(await api.get('/agents')).first['id']);
      final before = await fetchArtifacts(agentId: agentId);
      ArtifactRecord? created;
      try {
        created = await createTextArtifact(
          name: 'adopt-c-agent-note.txt',
          content: 'A reversible test file.',
          agentId: agentId,
        );
        expect(created.agentId, agentId);
        expect(created.threadId, isNull);
        final own = asJsonList(
          await api.get('/artifacts', query: {'agent_id': agentId}),
        );
        expect(own.map((r) => r['id']), contains(created.id));
        expect(own.every((r) => r['agent_id'] == agentId), isTrue);
        final library = await fetchArtifacts(agentId: agentId);
        expect(library.map((r) => r.id), contains(created.id));
      } finally {
        if (created != null) await deleteArtifact(created.id);
      }
      expect(
        (await fetchArtifacts(agentId: agentId)).map((r) => r.id).toSet(),
        before.map((r) => r.id).toSet(),
      );
    },
    skip: creds == null ? 'LONORA_TEST_CREDS not set' : false,
    timeout: const Timeout(Duration(minutes: 1)),
  );
}
