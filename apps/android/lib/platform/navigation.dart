// How platform surfaces (notification taps, heads-up banners, the incoming call's «reply with
// a message») open a route. They live above the app's Navigator, so they go through the root
// navigator's GoRouter. A location asked for before the owner is signed in and the router is
// up (a notification that cold-started the app) waits and opens once both are ready.
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';

import '../app/router.dart' show rootNavigatorKey;

abstract final class PlatformNavigation {
  /// Set by the app shell to route through its own router; by default the root navigator's
  /// GoRouter is used.
  static void Function(String location)? override;

  /// Whether a location may open now (the owner is signed in). Set by [PlatformServices].
  static bool Function() ready = () => true;

  static String? _pending;
  static int _retries = 0;

  /// The location waiting for sign-in / the router (tests).
  static String? get pending => _pending;

  /// Opens [location] now, or as soon as [flush] finds the app ready.
  static void open(String location) {
    _pending = location;
    _retries = 0;
    flush();
  }

  /// Opens the waiting location if the app can take it; returns whether it did.
  static bool flush() {
    final location = _pending;
    if (location == null || !ready()) return false;
    final custom = override;
    if (custom != null) {
      _pending = null;
      custom(location);
      return true;
    }
    final context = rootNavigatorKey.currentContext;
    final router = context == null ? null : GoRouter.maybeOf(context);
    if (router == null) {
      // The router is not built yet (cold start): try again after the next frames.
      if (_retries++ < 30) {
        WidgetsBinding.instance.addPostFrameCallback((_) => flush());
      }
      return false;
    }
    _pending = null;
    _retries = 0;
    // A conversation opened from outside lands on the chat list's stack (back returns there).
    scheduleMicrotask(() => router.go(location));
    return true;
  }

  static void clear() => _pending = null;
}
