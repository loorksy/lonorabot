// The server step: which Lonora server this app talks to, composed from the kit. Behaviour follows
// apps/mobile/app/server.tsx and sign-in.tsx: the address is normalised, a remote server must use
// https (http only for local addresses, apps/mobile/lib/connect-link.ts), and the server must
// answer `GET /onboarding` as Lonora before it is kept. Changing the server of a signed-in session
// signs out first (the old session is revoked), after a confirmation.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/session_actions.dart';
import '../../state/app_state.dart';
import '../settings/settings_common.dart';
import 'auth_widgets.dart';
import 'server_check.dart';

class ServerScreen extends StatefulWidget {
  const ServerScreen({super.key});

  @override
  State<ServerScreen> createState() => _ServerScreenState();
}

class _ServerScreenState extends State<ServerScreen> {
  late final TextEditingController _address;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final session = context.read().session;
    _address = TextEditingController(
      text: session.server ?? session.lastServer ?? '',
    );
  }

  @override
  void dispose() {
    _address.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_busy) return;
    final checked = checkServerAddress(_address.text);
    if (checked.server == null) {
      setState(() => _error = context.t(checked.error!));
      return;
    }
    final server = checked.server!;
    FocusScope.of(context).unfocus();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await probeOwnerInitialized(server);
    } catch (e) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = errorMessage(context, e);
        });
      }
      return;
    }
    if (!mounted) return;
    final session = context.read().session;
    if (session.signedIn) {
      if (sameServer(session.server!, server)) {
        setState(() => _busy = false);
        leavePage(context);
        return;
      }
      final confirmed = await showLnConfirm(
        context,
        title: context.t('server'),
        message: context.t('changeServerHint'),
        confirmLabel: context.t('save'),
        cancelLabel: context.t('sh_cancel'),
        destructive: true,
      );
      if (!confirmed || !mounted) {
        if (mounted) setState(() => _busy = false);
        return;
      }
    }
    try {
      await context.dispatchAndWait(ChangeServerAction(server));
      if (mounted) context.go(Routes.signIn);
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(context, e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final ln = context.ln;
    final signedIn = context.select((AppState s) => s.session.signedIn);
    // The first step of a phone with no server has nowhere to go back to.
    final canLeave = signedIn || context.canPop();
    return SettingsPageScaffold(
      title: context.t('server'),
      leading: canLeave ? null : const SizedBox.square(dimension: 48),
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: LnSpace.md),
              Center(
                child: Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(
                    color: ln.colors.fill1,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    FIcons.server,
                    size: 28,
                    color: ln.colors.fgMuted,
                  ),
                ),
              ),
              const SizedBox(height: LnSpace.lg),
              Text(
                context.t(signedIn ? 'changeServerHint' : 'serverHint'),
                style: ln.text.caption.copyWith(color: ln.colors.fgMuted),
              ),
              const SizedBox(height: LnSpace.lg),
              LtrField(
                label: context.t('server'),
                child: LnTextField(
                  controller: _address,
                  hint: 'https://lonora.example.com',
                  enabled: !_busy,
                  autofocus: _address.text.isEmpty,
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  textInputAction: TextInputAction.go,
                  autofillHints: const [AutofillHints.url],
                  onChanged: (_) => setState(() => _error = null),
                  onSubmitted: (_) => _save(),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: LnSpace.md),
                AuthNotice(text: _error!),
              ],
              const SizedBox(height: LnSpace.xl),
              BlockButton(
                label: context.t(
                  _busy ? 'connecting' : (signedIn ? 'save' : 'auth_continue'),
                ),
                loading: _busy,
                onPressed: _address.text.trim().isEmpty ? null : _save,
              ),
            ],
          ),
        ),
      ],
    );
  }
}
