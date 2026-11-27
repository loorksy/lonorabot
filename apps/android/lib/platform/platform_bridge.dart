// Dart side of MainActivity's `ai.lonora.android/platform` channel for this package: the
// phone's IANA time zone and another zone's offset (quiet hours), the installer (update
// channel) and the call's proximity screen-off. All answer null / do nothing where the channel
// is missing (tests, background isolates: the channel is registered only on the activity's
// engine).
import 'package:flutter/services.dart';

abstract final class PlatformBridge {
  static const channel = MethodChannel('ai.lonora.android/platform');

  /// `java.util.TimeZone.getDefault().id`, e.g. `Asia/Riyadh`.
  static Future<String?> timeZone() => _call<String>('timeZone');

  /// The UTC offset of the IANA [zone] at [at] (daylight saving included), in minutes; null
  /// for a zone the phone does not know.
  static Future<int?> zoneOffsetMinutes(String zone, DateTime at) =>
      _call<int>('zoneOffset', {'zone': zone, 'at': at.millisecondsSinceEpoch});

  /// While [on], the proximity sensor turns the screen off at the ear (a call on the
  /// earpiece); off releases it once nothing is near.
  static Future<void> proximityScreenOff(bool on) =>
      _call<void>('proximityScreenOff', {'on': on});

  /// The package that installed this app (`com.android.vending` for Google Play), or null
  /// for a sideloaded/adb install.
  static Future<String?> installerPackage() =>
      _call<String>('installerPackage');

  /// Opens an http(s) URL outside the app (the browser). False when nothing could open it.
  static Future<bool> openExternal(Uri url) async =>
      await _call<bool>('openExternal', {'url': url.toString()}) ?? false;

  static Future<T?> _call<T>(String method, [Object? arguments]) async {
    try {
      return await channel.invokeMethod<T>(method, arguments);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }
}
