import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app/app.dart';
import 'app/app_strings.dart';
import 'app/services.dart';
import 'app/teardown.dart';
import 'l10n/l10n.dart';
import 'platform/heads_up.dart';
import 'state/actions/session_actions.dart';
import 'state/app_state.dart';
import 'state/realtime.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Edge-to-edge: content draws behind transparent system bars.
  await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  await registerServices();
  await L10n.load();
  registerAllStrings();
  registerSignOutHooks();

  final store = Store<AppState>(
    initialState: const AppState(),
    defaultDistinct: true,
  );
  sl.registerSingleton<Store<AppState>>(store);
  realtime = RealtimeController(store);
  api.onUnauthorized = () => handleUnauthorized(store);
  unawaited(store.dispatchAndWait(BootstrapAction()));
  unawaited(PlatformServices.init());

  runApp(LonoraApp(store: store));
}
