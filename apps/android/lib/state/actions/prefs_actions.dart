import 'dart:async';
import 'dart:convert';

import 'dart:ui' show PlatformDispatcher;

import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../app/services.dart';
import '../../core/json.dart';
import '../../core/storage/local_store.dart';
import '../app_state.dart';
import 'base.dart';

const _themeKey = 'lonora.theme';
const _localeKey = 'lonora.locale';
const _chatPrefsKey = 'lonora.chatPrefs';
const _notifyInAppKey = 'lonora.notify.in_app';
const _notifyPreviewKey = 'lonora.notify.preview';
const _homeModeKey = 'lonora.homeMode';
const _lastThreadKey = 'lonora.lastThread';

const platformChannel = MethodChannel('ai.lonora.android/platform');

/// Device preferences survive sign-out (theme, language, conversation and notification
/// preferences).
class LoadPrefsAction extends AppAction {
  @override
  AppState reduce() {
    final theme = AppThemeMode.values.firstWhere(
      (m) => m.name == devicePrefs.getString(_themeKey),
      orElse: () => AppThemeMode.system,
    );
    final locale = devicePrefs.getString(_localeKey) ?? _systemDefaultLocale();
    ChatPrefs chat = const ChatPrefs();
    final raw = devicePrefs.getString(_chatPrefsKey);
    if (raw != null) {
      try {
        chat = ChatPrefs.fromJson(asJson(jsonDecode(raw)));
      } catch (_) {}
    }
    final home = HomeMode.values.firstWhere(
      (m) => m.name == devicePrefs.getString(_homeModeKey),
      orElse: () => HomeMode.lastChat,
    );
    _applyNativeNightMode(theme);
    return state.copyWith(
      prefs: PrefsState(
        themeMode: theme,
        locale: locale,
        chatPrefs: chat,
        notify: readNotifyPrefs(devicePrefs),
        homeMode: home,
      ),
    );
  }

  /// Lonora is Arabic-first; English when the phone itself is not in Arabic and is English.
  static String _systemDefaultLocale() {
    final system = PlatformDispatcher.instance.locale.languageCode;
    return system == 'en' ? 'en' : 'ar';
  }
}

void _applyNativeNightMode(AppThemeMode mode) {
  try {
    platformChannel
        .invokeMethod<void>('setNightMode', {'mode': mode.name})
        .catchError((Object _) {});
  } catch (_) {
    // No platform host (tests): the in-app theme still applies.
  }
}

class SetThemeModeAction extends AppAction {
  SetThemeModeAction(this.mode);
  final AppThemeMode mode;

  @override
  Future<AppState> reduce() async {
    await devicePrefs.setString(_themeKey, mode.name);
    _applyNativeNightMode(mode);
    return state.copyWith(prefs: state.prefs.copyWith(themeMode: mode));
  }
}

class SetLocaleAction extends AppAction {
  SetLocaleAction(this.locale);
  final String locale;

  @override
  Future<AppState> reduce() async {
    await devicePrefs.setString(_localeKey, locale);
    return state.copyWith(prefs: state.prefs.copyWith(locale: locale));
  }
}

/// Whether no language is stored, so the phone's decides (the rule of [LoadPrefsAction]).
bool get localeFollowsSystem => devicePrefs.getString(_localeKey) == null;

/// Forgets the stored language so the phone's decides (the rule of [LoadPrefsAction]).
class FollowSystemLocaleAction extends AppAction {
  @override
  Future<AppState> reduce() async {
    await devicePrefs.remove(_localeKey);
    return state.copyWith(
      prefs: state.prefs.copyWith(
        locale: LoadPrefsAction._systemDefaultLocale(),
      ),
    );
  }
}

/// The stored [NotifyPrefs] (both on when unset). The background check's isolate has no
/// store and reads them here too.
NotifyPrefs readNotifyPrefs(SharedPreferences prefs) => NotifyPrefs(
  inApp: prefs.getBool(_notifyInAppKey) ?? true,
  preview: prefs.getBool(_notifyPreviewKey) ?? true,
);

class SetNotifyPrefsAction extends AppAction {
  SetNotifyPrefsAction(this.prefs);
  final NotifyPrefs prefs;

  @override
  Future<AppState> reduce() async {
    await devicePrefs.setBool(_notifyInAppKey, prefs.inApp);
    await devicePrefs.setBool(_notifyPreviewKey, prefs.preview);
    return state.copyWith(prefs: state.prefs.copyWith(notify: prefs));
  }
}

class SetChatPrefsAction extends AppAction {
  SetChatPrefsAction(this.prefs);
  final ChatPrefs prefs;

  @override
  Future<AppState> reduce() async {
    await devicePrefs.setString(_chatPrefsKey, jsonEncode(prefs.toJson()));
    return state.copyWith(prefs: state.prefs.copyWith(chatPrefs: prefs));
  }
}

class SetHomeModeAction extends AppAction {
  SetHomeModeAction(this.mode);
  final HomeMode mode;

  @override
  Future<AppState> reduce() async {
    await devicePrefs.setString(_homeModeKey, mode.name);
    return state.copyWith(prefs: state.prefs.copyWith(homeMode: mode));
  }
}

/// Where the last opened conversation of the signed-in owner of this server is kept on this
/// device; null when signed out.
String? _lastThreadSlot(SessionState session) {
  final server = session.server;
  final owner = session.owner;
  if (server == null || owner == null) return null;
  return '$_lastThreadKey.${LocalStore.scope(server, owner.id)}';
}

SharedPreferences? get _prefsOrNull =>
    sl.isRegistered<SharedPreferences>() ? devicePrefs : null;

/// The conversation the owner of this server last opened on this device (the drawer home opens
/// on it), or null.
String? lastThreadOf(SessionState session) {
  final slot = _lastThreadSlot(session);
  if (slot == null) return null;
  final id = _prefsOrNull?.getString(slot);
  return id == null || id.isEmpty ? null : id;
}

/// Keeps [threadId] as the owner's last opened conversation; null forgets it.
void rememberLastThread(SessionState session, String? threadId) {
  final slot = _lastThreadSlot(session);
  final prefs = _prefsOrNull;
  if (slot == null || prefs == null) return;
  if (threadId == null || threadId.isEmpty) {
    unawaited(prefs.remove(slot));
  } else if (prefs.getString(slot) != threadId) {
    unawaited(prefs.setString(slot, threadId));
  }
}
