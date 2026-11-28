// Test harness for the WP-A2 pages (integrations, models, usage, running). It builds on the
// WP-A1 harness (scripted API, in-memory services, fonts, themes) and adds a store with shell
// data, a router with the destinations these pages open, and realistic server answers.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:async_redux/async_redux.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:lonora/app/routes.dart';
import 'package:lonora/app/services.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/core/realtime/lonora_event.dart';
import 'package:lonora/features/settings/integrations/integrations_strings.dart';
import 'package:lonora/features/settings/models/models_strings.dart';
import 'package:lonora/features/settings/running/running_strings.dart';
import 'package:lonora/features/settings/usage/usage_strings.dart';
import 'package:lonora/state/app_state.dart';
import 'package:lonora/state/realtime.dart';
import 'package:share_plus/share_plus.dart' show XFile;

import '../settings_core/feature_harness.dart';

export '../settings_core/feature_harness.dart';

/// Fonts, catalogs (with these pages' labels) and the A1 labels, once per test file.
Future<void> setUpExtTests() async {
  await setUpFeatureTests();
  registerIntegrationsStrings(testL10n);
  registerModelsStrings(testL10n);
  registerUsageStrings(testL10n);
  registerRunningStrings(testL10n);
}

/// [ScriptedApi] that also keeps each GET's query and answers CSV downloads.
class QueryApi extends ScriptedApi {
  final List<({String path, Map<String, Object?>? query})> gets = [];
  final List<({String path, String savePath, Map<String, Object?>? query})>
  downloads = [];

  @override
  Future<dynamic> get(
    String path, {
    Map<String, Object?>? query,
    Duration? timeout,
  }) {
    gets.add((path: path, query: query));
    return super.get(path, query: query, timeout: timeout);
  }

  @override
  Future<void> downloadTo(
    String path,
    String savePath, {
    Map<String, Object?>? query,
    void Function(int, int)? onProgress,
  }) async {
    downloads.add((path: path, savePath: savePath, query: query));
  }
}

/// Fresh services (the A1 harness's) with a [QueryApi] in place of its API; [routes] answer
/// it.
Future<QueryApi> setUpExtServices([void Function(QueryApi api)? routes]) async {
  await setUpServices();
  final api = QueryApi();
  routes?.call(api);
  sl
    ..unregister<ApiClient>()
    ..registerSingleton<ApiClient>(api);
  return api;
}

/// Platform channels the usage export touches (temporary directory, share sheet).
void mockExportChannels(List<MethodCall> shares) {
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(
    const MethodChannel('plugins.flutter.io/path_provider'),
    (call) async => Directory.systemTemp.path,
  );
  messenger.setMockMethodCallHandler(
    const MethodChannel('dev.fluttercommunity.plus/share'),
    (call) async {
      shares.add(call);
      return 'dev.fluttercommunity.plus/share/success';
    },
  );
}

/// A signed-in store with the given shell (agents in order, runs).
Store<AppState> extStore({
  String locale = 'en',
  AppThemeMode theme = AppThemeMode.light,
  List<Agent> agents = const [],
  List<Run> runs = const [],
}) {
  final store = Store<AppState>(
    initialState: AppState(
      session: const SessionState(
        status: SessionStatus.signedIn,
        server: testServer,
        owner: testOwner,
        lastServer: testServer,
        lastEmail: 'owner@example.com',
      ),
      shell: ShellState(
        agents: {for (final a in agents) a.id: a},
        agentOrder: [for (final a in agents) a.id],
        runs: runs,
        loaded: true,
      ),
      prefs: PrefsState(themeMode: theme, locale: locale),
    ),
  );
  realtime = RealtimeController(store);
  return store;
}

/// The page under test and stubs for every place it can open.
GoRouter extRouter(Widget home) => GoRouter(
  initialLocation: '/home',
  routes: [
    GoRoute(path: '/home', builder: (_, _) => home),
    for (final p in [
      Routes.models,
      Routes.agents,
      Routes.me,
      '/agent/:id/settings',
      '/chats/thread/:id',
      Routes.recovery,
    ])
      GoRoute(
        path: p,
        builder: (_, s) => StubPage(location: s.uri.toString()),
      ),
  ],
);

/// Pumps [page] in the app shell at the golden viewport.
Future<void> pumpExt(
  WidgetTester tester,
  Store<AppState> store,
  Widget page,
) async {
  setFeatureViewport(tester);
  await tester.pumpWidget(featureApp(store, extRouter(page)));
  await tester.pumpAndSettle();
}

Json j(Map<String, Object?> value) => value;

/// A picked file held in memory (no disk read inside the fake-async test zone).
final class MemoryPickedFile extends PlatformFile {
  MemoryPickedFile(this.name, String text)
    : _bytes = Uint8List.fromList(utf8.encode(text));

  @override
  final String name;
  final Uint8List _bytes;

  @override
  Uri get uri => Uri.file('/picked/$name');

  @override
  XFile get xFile => XFile.fromData(_bytes, name: name);

  @override
  int? lengthSync() => _bytes.length;

  @override
  Future<int?> length() async => _bytes.length;

  @override
  Future<Uint8List> readAsBytes() async => _bytes;

  @override
  Stream<Uint8List> readAsByteStream() => Stream.value(_bytes);
}

/// The system file picker answering [files] (empty: the owner cancelled).
class FakeFilePicker extends FilePickerPlatform {
  FakeFilePicker(this.files);

  final List<PlatformFile> files;
  final List<List<String>?> asked = [];

  @override
  Future<List<PlatformFile>> pickFiles({
    String? dialogTitle,
    String? initialDirectory,
    FileType type = FileType.any,
    List<String>? allowedExtensions,
    Function(FilePickerStatus)? onFileLoading,
    int compressionQuality = 0,
    AndroidOptions androidOptions = const AndroidOptions(),
    DarwinOptions darwinOptions = const DarwinOptions(),
    WindowsOptions windowsOptions = const WindowsOptions(),
    LinuxOptions linuxOptions = const LinuxOptions(),
    WebOptions webOptions = const WebOptions(),
  }) async {
    asked.add(allowedExtensions);
    return files;
  }
}

/// The event feed with events the test sends ([emit]) instead of a socket.
class ScriptedRealtime extends RealtimeController {
  ScriptedRealtime(super.store);

  final StreamController<LonoraEvent> _feed = StreamController.broadcast();

  @override
  Stream<LonoraEvent> get events => _feed.stream;

  void emit(String kind) =>
      _feed.add(LonoraEvent(cursor: 1, kind: kind, payload: const {}));
}
