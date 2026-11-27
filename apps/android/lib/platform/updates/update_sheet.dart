// The update prompt: a kit sheet with the version, Lonora's release notes, what will happen, and an
// explicit «تحديث» (Play) or «تنزيل» (the APK link in the browser) beside «لاحقًا»; once Play
// downloaded the update, «إعادة التشغيل» installs it. Nothing installs by itself.
import 'package:flutter/widgets.dart';

import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../platform_strings.dart';
import 'update_service.dart';

/// Shows [info]; resolves after the owner chose. Call from a screen inside the app navigator.
Future<void> showUpdateSheet(BuildContext context, UpdateInfo info) {
  registerPlatformStrings(context.l10n);
  final service = UpdateService.instance;
  return showLnSheet<void>(
    context,
    title: context.t('pf_updateAvailable'),
    builder: (sheet) => UpdateSheetBody(
      info: info,
      ready: info.downloaded || service.readyToRestart.value,
      onLater: () => Navigator.of(sheet).pop(),
      onUpdate: () async {
        // Play: its own dialog takes over and the download runs in the background (the app
        // asks for the restart when it is done), so the sheet closes at once.
        final started = await service.install(info);
        if (!sheet.mounted) return;
        Navigator.of(sheet).pop();
        if (!started && context.mounted) {
          LnToast.show(
            context,
            context.t('pf_updateFailed'),
            kind: LnToastKind.error,
          );
        }
      },
    ),
  );
}

/// «Check for updates» (e.g. the About screen's version row): an asked check, then the sheet,
/// or why there is nothing to install.
Future<void> checkForUpdates(BuildContext context) async {
  registerPlatformStrings(context.l10n);
  final service = UpdateService.instance;
  final info = await service.check(
    userInitiated: true,
    lang: Localizations.localeOf(context).languageCode,
  );
  if (!context.mounted) return;
  if (info != null) return showUpdateSheet(context, info);
  LnToast.show(
    context,
    context.t(
      service.lastCheckFailed
          ? 'pf_updateCheckFailed'
          : service.checksEnabled
          ? 'pf_upToDate'
          : 'pf_updatesOff',
    ),
    kind: service.lastCheckFailed ? LnToastKind.error : LnToastKind.notice,
  );
}

class UpdateSheetBody extends StatefulWidget {
  const UpdateSheetBody({
    super.key,
    required this.info,
    required this.onUpdate,
    required this.onLater,
    this.ready = false,
  });

  final UpdateInfo info;

  /// Play downloaded it: the button restarts the app to install it.
  final bool ready;
  final Future<void> Function() onUpdate;
  final VoidCallback onLater;

  @override
  State<UpdateSheetBody> createState() => _UpdateSheetBodyState();
}

class _UpdateSheetBodyState extends State<UpdateSheetBody> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    registerPlatformStrings(context.l10n);
    final ln = context.ln;
    final c = ln.colors;
    final info = widget.info;
    final notes = info.notes;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (info.versionName.isNotEmpty)
          Text(
            context.t('pf_updateVersion', [ltr(info.versionName)]),
            style: ln.text.captionStrong,
          ),
        if (notes != null) ...[
          const SizedBox(height: LnSpace.xs),
          Flexible(
            child: SingleChildScrollView(
              child: Text(
                notes,
                style: ln.text.caption,
                textDirection: textDirectionFor(
                  notes,
                  Directionality.of(context),
                ),
              ),
            ),
          ),
        ],
        const SizedBox(height: LnSpace.sm),
        Text(
          context.t(
            !info.viaStore
                ? 'pf_updateDownloadHint'
                : widget.ready
                ? 'pf_updateReady'
                : 'pf_updatePlayHint',
          ),
          style: ln.text.footnote.copyWith(color: c.fgMuted),
        ),
        const SizedBox(height: LnSpace.lg),
        BlockButton(
          label: context.t(
            !info.viaStore
                ? 'download'
                : widget.ready
                ? 'pf_restart'
                : 'pf_update',
          ),
          loading: _busy,
          onPressed: _busy
              ? null
              : () async {
                  setState(() => _busy = true);
                  await widget.onUpdate();
                  if (mounted) setState(() => _busy = false);
                },
        ),
        const SizedBox(height: LnSpace.xs),
        BlockButton(
          label: context.t('pf_updateLater'),
          variant: BlockButtonVariant.secondary,
          onPressed: _busy ? null : widget.onLater,
        ),
      ],
    );
  }
}
