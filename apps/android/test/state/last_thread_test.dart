// The last opened conversation (the drawer home opens on it) is kept on this device per server
// and owner: each owner of each server has their own; a signed-out session has none.
import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/state/actions/prefs_actions.dart';
import 'package:lonora/state/actions/thread_actions.dart';
import 'package:lonora/state/app_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

SessionState _session(String server, String owner) => SessionState(
  status: SessionStatus.signedIn,
  server: server,
  owner: Owner(id: owner, email: '$owner@example.com'),
);

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    if (sl.isRegistered<SharedPreferences>()) {
      await sl.unregister<SharedPreferences>();
    }
    sl.registerSingleton<SharedPreferences>(prefs);
  });

  test('kept per server and owner', () {
    final a = _session('https://one.example', 'o1');
    final b = _session('https://one.example', 'o2');
    final c = _session('https://two.example', 'o1');
    rememberLastThread(a, 't-a');
    rememberLastThread(b, 't-b');
    expect(lastThreadOf(a), 't-a');
    expect(lastThreadOf(b), 't-b');
    expect(lastThreadOf(c), isNull);
    rememberLastThread(a, null);
    expect(lastThreadOf(a), isNull);
    expect(lastThreadOf(const SessionState()), isNull);
  });

  test('a conversation that opens becomes the last one', () async {
    final session = _session('https://one.example', 'o1');
    final store = Store<AppState>(initialState: AppState(session: session));
    await store.dispatchAndWait(SetOpenThreadAction('t-7'));
    expect(store.state.openThreadId, 't-7');
    expect(lastThreadOf(session), 't-7');
    // Leaving a conversation keeps it.
    await store.dispatchAndWait(SetOpenThreadAction(null));
    expect(lastThreadOf(session), 't-7');
  });

  test('signed out, nothing is kept', () async {
    final store = Store<AppState>(initialState: const AppState());
    await store.dispatchAndWait(SetOpenThreadAction('t-7'));
    expect(store.state.openThreadId, 't-7');
    expect(
      (await SharedPreferences.getInstance()).getKeys().where(
        (k) => k.startsWith('lonora.lastThread'),
      ),
      isEmpty,
    );
  });
}
