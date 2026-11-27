// About: this app's version and build (AppInfo), «Check for updates» (or «Update available»
// once one was found, lib/platform/updates), the server's version (`GET /version`), the
// open-source licenses (read from Flutter's LicenseRegistry, shown in the app's own pages)
// and the way to Lonora on the web.
import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart' show LicenseEntry, LicenseRegistry;
import 'package:flutter/material.dart' show MaterialPageRoute;
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../app/routes.dart';
import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../platform/platform_strings.dart';
import '../../platform/updates/update_service.dart';
import '../../platform/updates/update_sheet.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import '../auth/server_check.dart';
import 'settings_common.dart';
import 'settings_core_data.dart';

class AboutScreen extends StatefulWidget {
  const AboutScreen({super.key});

  @override
  State<AboutScreen> createState() => _AboutScreenState();
}

class _AboutScreenState extends State<AboutScreen> {
  ServerVersion? _server;
  Object? _error;
  bool _checking = false;

  @override
  void initState() {
    super.initState();
    UpdateService.instance.available.addListener(_updateChanged);
    unawaited(_load());
  }

  @override
  void dispose() {
    UpdateService.instance.available.removeListener(_updateChanged);
    super.dispose();
  }

  void _updateChanged() => setState(() {});

  Future<void> _checkForUpdates() async {
    setState(() => _checking = true);
    await checkForUpdates(context);
    if (mounted) setState(() => _checking = false);
  }

  Future<void> _load() async {
    try {
      final version = await fetchServerVersion();
      if (mounted) {
        setState(() {
          _server = version;
          _error = null;
        });
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (!mounted) return;
      // A failed refresh keeps what is shown and says why.
      if (_server != null) {
        showErrorToast(context, e);
      } else {
        setState(() => _error = e);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    registerPlatformStrings(context.l10n);
    final ln = context.ln;
    final c = ln.colors;
    final info = appInfo;
    final update = UpdateService.instance.available.value;
    final server = context.select((AppState s) => s.session.server);
    final serverVersion = _server;
    return SettingsPageScaffold(
      title: context.t('me_about'),
      fallback: Routes.settings,
      onRefresh: _load,
      children: [
        const SizedBox(height: LnSpace.md),
        Center(
          child: Image.asset(
            'assets/brand/logo.png',
            width: 72,
            height: 72,
            excludeFromSemantics: true,
          ),
        ),
        const SizedBox(height: LnSpace.sm),
        Center(
          child: Text(
            context.t('set_versionLine', const [], {
              'version': ltr(info.version),
            }),
            style: ln.text.headline.copyWith(color: c.fg),
          ),
        ),
        const SizedBox(height: LnSpace.xs),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.xxl),
          child: Text(
            context.t('set_aboutBody'),
            textAlign: TextAlign.center,
            style: ln.text.caption.copyWith(color: c.fgMuted),
          ),
        ),
        const SizedBox(height: LnSpace.xl),
        LnSection(
          children: [
            LnListTile(
              icon: FIcons.smartphone,
              title: context.t('set_appVersion'),
              value: ltr('${info.version} (${info.buildNumber})'),
            ),
            if (update != null)
              LnListTile(
                icon: FIcons.download,
                title: context.t('pf_updateAvailable'),
                value: update.versionName.isEmpty
                    ? null
                    : ltr(update.versionName),
                onTap: () => showUpdateSheet(context, update),
              )
            else
              LnListTile(
                icon: FIcons.refreshCw,
                title: context.t('pf_checkForUpdates'),
                trailing: _checking ? const LnSpinner(size: 16) : null,
                onTap: _checking ? null : _checkForUpdates,
              ),
            LnListTile(
              icon: FIcons.server,
              title: context.t('set_serverVersion'),
              value: serverVersion != null
                  ? ltr(serverVersion.label)
                  : (_error != null ? null : context.t('sh_loading')),
              subtitle: serverVersion == null && _error != null
                  ? errorMessage(context, _error!)
                  : (server == null ? null : ltr(serverHost(server))),
              onTap: serverVersion == null && _error != null ? _load : null,
            ),
          ],
        ),
        const SectionGap(),
        LnSection(
          children: [
            if (server != null)
              // Leaves the app: the up-right arrow instead of the chevron.
              LnListTile(
                icon: FIcons.globe,
                title: context.t('set_openWeb'),
                external: true,
                onTap: () => openExternalUrl(context, Uri.parse('$server/app')),
              ),
            LnListTile(
              icon: FIcons.scrollText,
              title: context.t('set_licenses'),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute<void>(builder: (_) => const LicensesPage()),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// The open-source packages in this app, A to Z; each opens its license texts.
class LicensesPage extends StatefulWidget {
  const LicensesPage({super.key});

  @override
  State<LicensesPage> createState() => _LicensesPageState();
}

class _LicensesPageState extends State<LicensesPage> {
  SplayTreeMap<String, List<LicenseEntry>>? _packages;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final packages = SplayTreeMap<String, List<LicenseEntry>>(
      (a, b) => a.toLowerCase().compareTo(b.toLowerCase()),
    );
    await for (final entry in LicenseRegistry.licenses) {
      for (final package in entry.packages) {
        packages.putIfAbsent(package, () => []).add(entry);
      }
    }
    if (mounted) setState(() => _packages = packages);
  }

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final packages = _packages;
    return SettingsPageScaffold(
      title: context.t('set_licenses'),
      body: packages == null
          ? const SettingsSkeleton(groups: [6])
          : packages.isEmpty
          ? EmptyState(
              icon: FIcons.scrollText,
              title: context.t('set_licenses'),
            )
          : null,
      children: [
        if (packages != null && packages.isNotEmpty)
          LnSection(
            children: [
              for (final MapEntry(key: name, value: entries)
                  in packages.entries)
                LnListTile(
                  title: name,
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) =>
                          _LicenseTextPage(package: name, entries: entries),
                    ),
                  ),
                ),
            ],
          ),
      ],
    );
  }
}

/// One package's license texts (English, left to right), as the registry gives them.
class _LicenseTextPage extends StatelessWidget {
  const _LicenseTextPage({required this.package, required this.entries});

  final String package;
  final List<LicenseEntry> entries;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final style = ln.text.footnote.copyWith(color: ln.colors.fg);
    return SettingsPageScaffold(
      title: package,
      children: [
        Directionality(
          textDirection: TextDirection.ltr,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: LnSpace.pageGutter),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final (i, entry) in entries.indexed) ...[
                  if (i > 0) const SizedBox(height: LnSpace.xxl),
                  for (final paragraph in entry.paragraphs)
                    Padding(
                      padding: EdgeInsets.only(
                        bottom: LnSpace.xs,
                        left: paragraph.indent > 0
                            ? paragraph.indent * LnSpace.md
                            : 0,
                      ),
                      child: Text(
                        paragraph.text,
                        style: style,
                        textAlign: paragraph.indent < 0
                            ? TextAlign.center
                            : TextAlign.start,
                      ),
                    ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}
