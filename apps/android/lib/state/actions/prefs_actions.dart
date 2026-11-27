import 'dart:convert';

import 'dart:ui' show PlatformDispatcher;

import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../app/services.dart';
import '../../core/json.dart';
import '../app_state.dart';
import 'base.dart';

const _themeKey = 'lonora.theme';
const _localeKey = 'lonora.locale';
const _chatPrefsKey = 'lonora.chatPrefs';
const _notifyInAppKey = 'lonora.notify.in_app';
const _notifyPreviewKey = 'lonora.notify.preview';

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
    _applyNativeNightMode(theme);
    return state.copyWith(
      prefs: PrefsState(
        themeMode: theme,
        locale: locale,
        chatPrefs: chat,
        notify: readNotifyPrefs(devicePrefs),
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
