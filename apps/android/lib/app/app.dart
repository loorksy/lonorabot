import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:forui/forui.dart';
import 'package:go_router/go_router.dart';

import '../design/design.dart';
import '../features/share/share_picker.dart';
import '../l10n/l10n.dart';
import '../platform/heads_up.dart';
import '../state/actions/shell_actions.dart';
import '../state/actions/thread_actions.dart';
import '../state/app_state.dart';
import '../state/realtime.dart';
import 'deep_links.dart';
import 'router.dart';

class LonoraApp extends StatefulWidget {
  const LonoraApp({super.key, required this.store});
  final Store<AppState> store;

  @override
  State<LonoraApp> createState() => _LonoraAppState();
}

class _LonoraAppState extends State<LonoraApp> with WidgetsBindingObserver {
  late final GoRouter _router = buildRouter(widget.store);
  StreamSubscription<List<ConnectivityResult>>? _connectivity;
  List<ConnectivityResult>? _lastConnectivity;
  late final DeepLinks _links = DeepLinks(store: widget.store, router: _router);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _connectivity = Connectivity().onConnectivityChanged.listen(
      _onConnectivity,
    );
    _links.start();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectivity?.cancel();
    _links.dispose();
    super.dispose();
  }

  /// The feed is closed in the background and resumed (from the last cursor) on foreground,
  /// followed by a snapshot refresh; agents keep working on the server meanwhile.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final store = widget.store;
    if (!store.state.session.signedIn) return;
    switch (state) {
      case AppLifecycleState.resumed:
        realtime.resume();
        store.dispatch(RefreshShellAction());
        final open = store.state.openThreadId;
        if (open != null) store.dispatch(LoadThreadAction(open));
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
        realtime.pause();
      case AppLifecycleState.inactive:
      case AppLifecycleState.detached:
        break;
    }
  }

  void _onConnectivity(List<ConnectivityResult> results) {
    final previous = _lastConnectivity;
    _lastConnectivity = results;
    if (previous == null || !widget.store.state.session.signedIn) return;
    final online = !results.contains(ConnectivityResult.none);
    if (online && previous.toString() != results.toString()) {
      // A new network: replace the socket (the old one may be silently dead) and flush.
      realtime.resume();
      widget.store.dispatch(FlushOutboxAction());
    }
  }

  @override
  Widget build(BuildContext context) {
    return StoreProvider<AppState>(
      store: widget.store,
      child: StoreConnector<AppState, ({AppThemeMode mode, String locale})>(
        converter: (store) => (
          mode: store.state.prefs.themeMode,
          locale: store.state.prefs.locale,
        ),
        builder: (context, vm) {
          final locale = Locale(vm.locale);
          L10n.instance.setLocale(locale);
          return MaterialApp.router(
            title: 'Lonora',
            debugShowCheckedModeBanner: false,
            routerConfig: _router,
            locale: locale,
            supportedLocales: L10n.supportedLocales,
            localizationsDelegates: [
              L10n.instance.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
              ...FLocalizations.localizationsDelegates,
            ],
            themeMode: switch (vm.mode) {
              AppThemeMode.system => ThemeMode.system,
              AppThemeMode.light => ThemeMode.light,
              AppThemeMode.dark => ThemeMode.dark,
            },
            theme: lnMaterialTheme(LnPalette.light),
            darkTheme: lnMaterialTheme(LnPalette.dark),
            builder: (context, child) {
              final brightness = switch (vm.mode) {
                AppThemeMode.light => Brightness.light,
                AppThemeMode.dark => Brightness.dark,
                AppThemeMode.system => MediaQuery.platformBrightnessOf(context),
              };
              final palette = brightness == Brightness.dark
                  ? LnPalette.dark
                  : LnPalette.light;
              return LnTheme(
                data: LnThemeData.fromPalette(palette),
                child: FTheme(
                  data: lnForuiTheme(palette),
                  child: FToaster(
                    child: PlatformOverlayHost(
                      child: ShareListener(
                        navigatorKey: rootNavigatorKey,
                        child: child ?? const SizedBox.shrink(),
                      ),
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
