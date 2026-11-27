import 'dart:async';

import '../../app/services.dart';
import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../core/models/models.dart';
import '../../core/storage/secure_store.dart';
import '../app_state.dart';
import '../realtime.dart';
import 'base.dart';
import 'prefs_actions.dart';
import 'shell_actions.dart';

/// Restores device prefs and the stored session at launch. A stored session is trusted
/// optimistically (cached data shows at once) and verified with `GET /auth/session`.
class BootstrapAction extends AppAction {
  @override
  Future<AppState?> reduce() async {
    await dispatchAndWait(LoadPrefsAction());
    final stored = await secureStore.readSession();
    final remembered = await secureStore.lastServer();
    // A remote plain-http server (saved by an older build) is never used again: its token is
    // dropped unsent, and the owner picks an https address.
    final lastServer = remembered != null && serverAllowed(remembered)
        ? remembered
        : null;
    final lastEmail = await secureStore.lastEmail();
    if (stored != null && !serverAllowed(stored.server)) {
      await secureStore.clearSession();
      return state.copyWith(
        session: state.session.copyWith(
          status: SessionStatus.signedOut,
          lastServer: lastServer,
          lastEmail: lastEmail,
        ),
      );
    }
    if (stored == null ||
        (stored.expiresAt != null &&
            stored.expiresAt!.isBefore(DateTime.now()))) {
      if (stored != null) await secureStore.clearSession();
      return state.copyWith(
        session: state.session.copyWith(
          status: SessionStatus.signedOut,
          lastServer: lastServer,
          lastEmail: lastEmail,
          expired: stored != null,
        ),
      );
    }
    apiClient.configure(server: stored.server, token: stored.token);
    final owner = Owner(id: stored.ownerId, email: stored.email);
    dispatch(
      _SignedInAction(
        server: stored.server,
        owner: owner,
        lastEmail: lastEmail,
      ),
    );
    dispatch(RestoreShellCacheAction());
    unawaited(_verify());
    return null;
  }

  Future<void> _verify() async {
    try {
      await apiClient.get('/auth/session');
    } on ApiError catch (e) {
      if (e.isUnauthorized) {
        dispatch(SignOutAction(expired: true, revoke: false));
      }
    } catch (_) {
      // Offline at launch: keep the cached session; the realtime feed retries.
    }
  }
}

class _SignedInAction extends AppAction {
  _SignedInAction({required this.server, required this.owner, this.lastEmail});
  final String server;
  final Owner owner;
  final String? lastEmail;

  @override
  AppState reduce() {
    final next = state.copyWith(
      session: state.session.copyWith(
        status: SessionStatus.signedIn,
        server: server,
        owner: owner,
        lastServer: server,
        lastEmail: lastEmail ?? owner.email,
        expired: false,
        pendingSetupToken: null,
      ),
    );
    return next;
  }

  @override
  void after() {
    realtime.startFor(server: server);
    dispatch(RefreshShellAction());
  }
}

/// `POST /api/auth/mobile/login` → opaque bearer stored in secure storage.
class SignInAction extends AppAction {
  SignInAction({
    required this.server,
    required this.email,
    required this.password,
  });
  final String server;
  final String email;
  final String password;

  @override
  Future<AppState?> reduce() async {
    final previousServer = apiClient.server;
    apiClient.configure(server: server, token: null);
    try {
      final data = asJson(
        await apiClient.post('/auth/mobile/login', {
          'email': email.trim(),
          'password': password,
        }),
      );
      final token = asString(data['token']);
      final ownerJson = asJson(data['owner']);
      if (token == null || ownerJson.isEmpty) {
        throw ApiError(status: 500, code: 'request_failed');
      }
      final expiresIn = asInt(data['expires_in']);
      final owner = Owner(
        id: asStr(ownerJson['id']),
        email: asStr(ownerJson['email'], email.trim()),
      );
      await secureStore.writeSession(
        StoredSession(
          server: server,
          token: token,
          ownerId: owner.id,
          email: owner.email,
          expiresAt: expiresIn == null
              ? null
              : DateTime.now().add(Duration(seconds: expiresIn)),
        ),
      );
      apiClient.configure(server: server, token: token);
      dispatch(
        _SignedInAction(server: server, owner: owner, lastEmail: owner.email),
      );
      dispatch(RestoreShellCacheAction());
      return null;
    } catch (_) {
      if (previousServer != null && previousServer != server) {
        apiClient.configure(server: previousServer, token: null);
      }
      rethrow;
    }
  }
}

/// First run: `POST /api/onboarding` with the server's bootstrap token, then sign in.
/// `409 owner_already_initialized` counts as success (apps/mobile/lib/session.tsx:128-143).
class SetupOwnerAction extends AppAction {
  SetupOwnerAction({
    required this.server,
    required this.email,
    required this.password,
    required this.bootstrapToken,
  });
  final String server;
  final String email;
  final String password;
  final String bootstrapToken;

  @override
  Future<AppState?> reduce() async {
    try {
      await apiClient.probe(
        server,
        '/onboarding',
        method: 'POST',
        body: {
          'email': email.trim(),
          'password': password,
          'bootstrap_token': bootstrapToken.trim(),
        },
      );
    } on ApiError catch (e) {
      if (e.code != 'owner_already_initialized') rethrow;
    }
    await dispatchAndWait(
      SignInAction(server: server, email: email, password: password),
    );
    return null;
  }
}

/// Ends the session. [revoke] calls `POST /auth/logout` (revokes this session and its push
/// registrations); [expired] marks a server-side expiry so sign-in can explain it.
class SignOutAction extends AppAction {
  SignOutAction({this.expired = false, this.revoke = true});
  final bool expired;
  final bool revoke;

  /// The sign-out under way: another one meanwhile (a 401 while this one revokes) waits for
  /// it and changes nothing.
  static Future<void>? _inFlight;

  @override
  Future<AppState?> reduce() async {
    if (!state.session.signedIn &&
        state.session.status != SessionStatus.unknown) {
      return null;
    }
    final running = _inFlight;
    if (running != null) {
      await running;
      return null;
    }
    final done = Completer<void>();
    _inFlight = done.future;
    try {
      final scope = cacheScope;
      if (revoke) {
        // As Expo's logout (apps/mobile/lib/session.tsx): what still needs the session (the
        // voice call's server close) runs alongside the revocation; a failing or slow hook
        // never prevents it nor holds sign-out longer than [beforeSignOutTimeout].
        await Future.wait([
          for (final hook in List.of(beforeSignOutHooks)) _bounded(hook),
          _revoke(),
        ]);
      }
      realtime.stop();
      await secureStore.clearSession();
      // The session fence: whatever a hook still has in flight is cancelled here.
      apiClient.configure(server: state.session.server, token: null);
      if (scope != null && revoke) await localStore.clearScope(scope);
      for (final hook in signOutHooks) {
        await hook();
      }
      return state.signedOut(
        session: SessionState(
          status: SessionStatus.signedOut,
          lastServer: state.session.server,
          lastEmail: state.session.owner?.email,
          expired: expired,
        ),
      );
    } finally {
      _inFlight = null;
      done.complete();
    }
  }

  Future<void> _revoke() async {
    try {
      await apiClient.post('/auth/logout').timeout(const Duration(seconds: 8));
    } catch (_) {
      // Sign-out is local-first: the token is dropped even when the server is unreachable.
    }
  }

  static Future<void> _bounded(Future<void> Function() hook) async {
    try {
      await hook().timeout(beforeSignOutTimeout);
    } catch (_) {}
  }
}

/// Teardown that still needs the session (the voice call closes on the server), run alongside
/// `POST /auth/logout` when the owner signs out; not on an expiry, where the token is gone.
final List<Future<void> Function()> beforeSignOutHooks = [];

/// The longest a [beforeSignOutHooks] entry holds sign-out.
const beforeSignOutTimeout = Duration(seconds: 3);

/// Teardown hooks registered by features (voice, notifications, background sync), run once
/// the token is dropped, on every sign-out and expiry.
final List<Future<void> Function()> signOutHooks = [];

/// Changing server always signs out first (the old session is revoked). A connect link's
/// setup token stays only for its own server (`sameServer`). A remote plain-http server is
/// refused ([serverAllowed]).
class ChangeServerAction extends AppAction {
  ChangeServerAction(this.server);
  final String server;

  @override
  Future<AppState?> reduce() async {
    if (!serverAllowed(server)) throw httpsRequired();
    if (state.session.signedIn) await dispatchAndWait(SignOutAction());
    await secureStore.rememberServer(server);
    final held = state.session.pendingSetupToken;
    final heldServer = held == null ? null : normalizeServerUrl(held.server);
    final sameServer =
        heldServer != null && heldServer == normalizeServerUrl(server);
    return state.copyWith(
      session: state.session.copyWith(
        lastServer: server,
        pendingSetupToken: sameServer ? held : null,
      ),
    );
  }
}

/// A validated `lonora://connect` link: hold the setup token in memory for that server. A
/// remote plain-http server is refused ([serverAllowed]).
class ConnectLinkAction extends AppAction {
  ConnectLinkAction({required this.server, this.token});
  final String server;
  final String? token;

  @override
  Future<AppState?> reduce() async {
    if (!serverAllowed(server)) throw httpsRequired();
    if (state.session.signedIn && state.session.server != server) {
      await dispatchAndWait(SignOutAction());
    }
    await secureStore.rememberServer(server);
    return state.copyWith(
      session: state.session.copyWith(
        lastServer: server,
        pendingSetupToken: token == null
            ? null
            : (server: server, token: token!),
      ),
    );
  }
}
