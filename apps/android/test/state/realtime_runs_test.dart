// A run transition that carries no run snapshot still moves the owner-wide run list, so the
// chats list's "Working…" follows a run whose conversation is not loaded.
import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';

void main() {
  testWidgets('run.completed without a snapshot updates shell.runs', (
    tester,
  ) async {
    {
      final queued = Run.fromJson({
        'id': 'r1',
        'thread_id': 't1',
        'agent_id': 'a1',
        'status': 'running',
      });
      final store = Store<AppState>(
        initialState: AppState(shell: ShellState(runs: [queued])),
      );
      store.dispatch(
        ApplyEventAction(
          const LonoraEvent(
            cursor: 9,
            kind: 'run.completed',
            threadId: 't1',
            runId: 'r1',
          ),
        ),
      );
      await tester.pump();
      expect(store.state.shell.runs.single.status, 'completed');
      expect(store.state.threads['t1'], isNull);
      // The debounced snapshot refetch has no server here; it must not throw.
      await tester.pump(const Duration(seconds: 1));
    }
  });

  testWidgets('an unknown run without a snapshot changes nothing', (
    tester,
  ) async {
    {
      final store = Store<AppState>(initialState: const AppState());
      store.dispatch(
        ApplyEventAction(
          const LonoraEvent(
            cursor: 1,
            kind: 'run.running',
            threadId: 't1',
            runId: 'rX',
          ),
        ),
      );
      await tester.pump();
      expect(store.state.shell.runs, isEmpty);
      await tester.pump(const Duration(seconds: 1));
    }
  });
}
