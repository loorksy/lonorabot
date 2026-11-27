// The event feed follows the server-address rule: a remote plain-http server is never
// contacted, so the bearer token never travels in clear.
import 'package:async_redux/async_redux.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../features/settings_core/feature_harness.dart';

void main() {
  test('a remote plain-http server opens no feed', () async {
    SharedPreferences.setMockInitialValues({});
    final client = ApiClient(userAgent: 'Lonora-Android/test');
    await registerServices(
      apiClient: client,
      secure: MemorySecureStore(),
      local: MemoryLocalStore(),
      prefs: await SharedPreferences.getInstance(),
      info: const AppInfo(
        version: '1.0.0',
        buildNumber: '7',
        packageName: 'ai.lonora.android',
      ),
    );
    client.configure(server: 'https://lonora.example.com', token: 'T' * 24);
    final controller = RealtimeController(
      Store<AppState>(initialState: const AppState()),
    );

    controller.startFor(server: 'http://lonora.example.com');
    expect(controller.status, StreamStatus.idle);
  });
}
