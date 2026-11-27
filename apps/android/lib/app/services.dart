import 'package:async_redux/async_redux.dart';
import 'package:get_it/get_it.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/api/api_client.dart';
import '../core/storage/local_store.dart';
import '../core/storage/secure_store.dart';
import '../state/app_state.dart';

/// Service locator (get_it). Feature code reads services through these getters; tests register
/// fakes with [registerServices].
final GetIt sl = GetIt.instance;

ApiClient get api => sl<ApiClient>();
SecureStore get secureStore => sl<SecureStore>();
LocalStore get localStore => sl<LocalStore>();
SharedPreferences get devicePrefs => sl<SharedPreferences>();
AppInfo get appInfo => sl<AppInfo>();

/// The app store, for services that live outside the widget tree (notifications, calls).
Store<AppState> get appStore => sl<Store<AppState>>();

class AppInfo {
  const AppInfo({
    required this.version,
    required this.buildNumber,
    required this.packageName,
  });
  final String version;
  final String buildNumber;
  final String packageName;

  String get userAgent => 'Lonora-Android/$version+$buildNumber';
}

Future<void> registerServices({
  ApiClient? apiClient,
  SecureStore? secure,
  LocalStore? local,
  SharedPreferences? prefs,
  AppInfo? info,
}) async {
  await sl.reset();
  final resolvedInfo = info ?? await _appInfo();
  sl.registerSingleton<AppInfo>(resolvedInfo);
  sl.registerSingleton<ApiClient>(
    apiClient ?? ApiClient(userAgent: resolvedInfo.userAgent),
  );
  sl.registerSingleton<SecureStore>(secure ?? SecureStore());
  sl.registerSingleton<LocalStore>(local ?? await LocalStore.open());
  sl.registerSingleton<SharedPreferences>(
    prefs ?? await SharedPreferences.getInstance(),
  );
}

Future<AppInfo> _appInfo() async {
  try {
    final p = await PackageInfo.fromPlatform();
    return AppInfo(
      version: p.version,
      buildNumber: p.buildNumber,
      packageName: p.packageName,
    );
  } catch (_) {
    return const AppInfo(
      version: '0.0.0',
      buildNumber: '0',
      packageName: 'ai.lonora.android',
    );
  }
}
