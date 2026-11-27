// The cards' side reads against a REAL disposable Lonora server (read-only GETs): every thread's
// owner actions, trade approvals, execution receipts and peer exchanges load into
// `ThreadState.side`, each owner action renders through the shared spec, and every row gets a
// timeline place. Nothing is decided or executed.
//
// Runs only when LONORA_TEST_CREDS points at {server_url, bearer_token} of a disposable test
// server (see docs/android/analysis/lonora-local-runtime.md). Never point it at production.
import 'dart:convert';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/features/cards/cards_actions.dart';
import 'package:lonora/features/cards/thread_cards.dart';
import 'package:lonora/l10n/l10n.dart';
import 'package:lonora/state/app_state.dart';

import '../rich/rich_harness.dart';

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
  });

  test(
    'side reads of every thread load, render and get a timeline place',
    () async {
      final threads = asJsonList(await api.get('/threads'));
      expect(threads, isNotEmpty);
      final store = Store<AppState>(initialState: signedInState());
      var ownerActions = 0;
      for (final thread in threads) {
        final id = asStr(thread['id']);
        await store.dispatchAndWait(LoadThreadSideAction(id));
        final t = store.state.thread(id);
        for (final key in [
          SideKeys.ownerActions,
          SideKeys.approvals,
          SideKeys.receipts,
          SideKeys.peerMessages,
        ]) {
          expect(t.side[key], isA<List>(), reason: '$key of $id');
        }
        for (final row in sideList(t, SideKeys.ownerActions)) {
          ownerActions++;
          expect(row['thread_id'], id);
          for (final locale in ['ar', 'en']) {
            final spec = ownerActionCard(row, locale, DateTime.now());
            expect(spec.title, isNotEmpty);
            if (row['status'] == 'pending') expect(spec.buttons, isNotEmpty);
          }
        }
        final anchors = cardAnchors(
          messages: const [],
          approvals: sideList(t, SideKeys.approvals),
          ownerActions: sideList(t, SideKeys.ownerActions),
          receipts: sideList(t, SideKeys.receipts),
        );
        expect(
          anchors.length,
          sideList(t, SideKeys.approvals).length +
              sideList(t, SideKeys.ownerActions).length +
              sideList(t, SideKeys.receipts).length,
        );
      }
      // The disposable server raises the Mandate card for its trading agent.
      expect(ownerActions, greaterThan(0));
    },
    skip: creds == null ? 'LONORA_TEST_CREDS not set' : false,
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
