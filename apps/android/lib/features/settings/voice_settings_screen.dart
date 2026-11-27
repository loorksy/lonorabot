// Voice, built from forui tile groups. Lonora's voice settings are read-only on every
// client (apps/mobile/app/(settings)/voice.tsx, apps/web VoiceSettingsOverlay.tsx): the server's
// GPT-Live status and model (`GET /voice/status`); the voice model is chosen in global model
// routing. Android adds the microphone permission calls need, and Expo's note on where calls
// start (its last sentence told as Android runs calls: on in the background).
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../app/routes.dart';
import '../../core/api/api_error.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import 'settings_common.dart';
import 'settings_core_data.dart';

class VoiceSettingsScreen extends StatefulWidget {
  const VoiceSettingsScreen({super.key});

  @override
  State<VoiceSettingsScreen> createState() => _VoiceSettingsScreenState();
}

class _VoiceSettingsScreenState extends State<VoiceSettingsScreen>
    with WidgetsBindingObserver {
  VoiceStatus? _status;
  Object? _error;
  PermissionStatus? _mic;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_load());
    unawaited(_readMic());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_readMic());
  }

  Future<void> _load() async {
    try {
      final status = await fetchVoiceStatus();
      if (mounted) {
        setState(() {
          _status = status;
          _error = null;
        });
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (!mounted) return;
      // A failed refresh keeps what is shown and says why.
      if (_status != null) {
        showErrorToast(context, e);
      } else {
        setState(() => _error = e);
      }
    }
  }

  Future<void> _readMic() async {
    try {
      final status = await Permission.microphone.status;
      if (mounted) setState(() => _mic = status);
    } catch (_) {
      // No permission plugin on this host.
    }
  }

  Future<void> _microphone() async {
    final status = _mic;
    if (status != null && status.isDenied) {
      final next = await Permission.microphone.request();
      if (mounted) setState(() => _mic = next);
      return;
    }
    await openAppSettings();
  }

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final status = _status;
    final server = context.select((AppState s) => s.session.server);
    final mic = _mic;
    final micAllowed = mic != null && mic.isGranted;
    Widget? body;
    if (status == null) {
      body = _error != null
          ? LoadFailure(error: _error!, onRetry: _load)
          : const SettingsSkeleton(groups: [2, 1, 1]);
    }
    return SettingsPageScaffold(
      title: context.t('voice'),
      onRefresh: () async {
        await Future.wait([_load(), _readMic()]);
      },
      body: body,
      children: status == null
          ? const []
          : [
              LnSection(
                title: context.t('set_voiceTitle'),
                footer: status.configured
                    ? context.t('set_voiceBody')
                    : context.t('voice_transport_unconfigured'),
                children: [
                  LnListTile(
                    icon: FIcons.audioLines,
                    title: 'GPT-Live',
                    trailing: StatusChip(
                      label: context.t(
                        status.configured ? 'configured' : 'notConfigured',
                      ),
                      kind: status.configured
                          ? StatusChipKind.success
                          : StatusChipKind.neutral,
                    ),
                  ),
                  if (status.model != null)
                    LnListTile(
                      icon: FIcons.cpu,
                      title: context.t('set_voiceModel'),
                      value: ltr(status.model!),
                    ),
                ],
              ),
              const SectionGap(),
              SettingsNote(context.t('set_callHint')),
              LnSection(
                footer: context.t('set_voiceRouting'),
                children: [
                  LnListTile(
                    icon: FIcons.cpu,
                    title: context.t('models'),
                    onTap: () => context.push(Routes.models),
                  ),
                ],
              ),
              const SectionGap(),
              LnSection(
                title: context.t('set_thisPhone'),
                footer: context.t('set_micNote'),
                children: [
                  LnListTile(
                    icon: FIcons.mic,
                    title: context.t('set_microphone'),
                    subtitle: mic == null
                        ? null
                        : context.t(
                            micAllowed ? 'set_micAllowed' : 'set_micBlocked',
                          ),
                    value: mic == null || micAllowed
                        ? null
                        : context.t(
                            mic.isDenied
                                ? 'set_allow'
                                : 'set_openPhoneSettings',
                          ),
                    onTap: micAllowed ? null : _microphone,
                  ),
                ],
              ),
              if (server != null) ...[
                const SectionGap(),
                LnSection(
                  children: [
                    LnListTile(
                      icon: FIcons.externalLink,
                      title: context.t('openWebSettings'),
                      onTap: () => openExternalUrl(
                        context,
                        Uri.parse('$server/app?settings=voice'),
                      ),
                    ),
                  ],
                ),
              ],
            ],
    );
  }
}
