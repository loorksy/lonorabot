import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';

import '../../app/services.dart';
import '../../core/api/api_client.dart';
import '../../core/storage/local_store.dart';
import '../app_state.dart';

/// Base of every Lonora action. Gives access to services and the owner-scoped cache key.
abstract class AppAction extends ReduxAction<AppState> {
  ApiClient get apiClient => api;

  /// LocalStore scope for the signed-in owner, or null when signed out.
  String? get cacheScope {
    final s = state.session;
    final owner = s.owner;
    final server = s.server;
    if (owner == null || server == null) return null;
    return LocalStore.scope(server, owner.id);
  }

  bool get signedIn => state.session.signedIn;
}

extension AppStoreContext on BuildContext {
  AppState get state => getState<AppState>();
  AppState read() => getRead<AppState>();
  R select<R>(R Function(AppState state) selector) =>
      getSelect<AppState, R>(selector);
}
