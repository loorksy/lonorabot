// `lonora://connect?server=…&token=…` (Lonora Cloud's "Open in the app"). Composed from the kit.
// Behaviour and wording follow apps/mobile/app/connect.tsx: the host is shown and nothing
// happens until the owner confirms; a remote server must use https (http only for local
// addresses); the setup token is held in memory for that server only (ConnectLinkAction).
// Confirming while signed in to another server signs out there (the session is revoked), which
// the screen says first, as the server step does; the screen cannot be left while connecting.
import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart' show SelectableText;
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

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key, required this.server, this.token});
  final String server;
  final String? token;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  bool _busy = false;
  String? _error;

  static final _tokenPattern = RegExp(r'^[A-Za-z0-9_-]{20,128}$');

  /// The link's server, or null when it is not a valid connect link.
  String? get _server {
    if (widget.server.length > 300) return null;
    return checkServerAddress(widget.server).server;
  }

  String? get _token {
    final t = widget.token;
    return t != null && _tokenPattern.hasMatch(t) ? t : null;
  }

  void _notNow() {
    final signedIn = context.read().session.signedIn;
    context.go(signedIn ? Routes.chats : Routes.signIn);
  }

  Future<void> _connect(String server) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await context.dispatchAndWait(
        ConnectLinkAction(server: server, token: _token),
      );
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
    final c = ln.colors;
    final server = _server;
    final session = context.select((AppState s) => s.session);
    final revokes =
        server != null &&
        session.signedIn &&
        !sameServer(session.server!, server);
    return PopScope(
      canPop: !_busy,
      child: SettingsPageScaffold(
        title: context.t('connectTitle'),
        leading: CircleIconButton(
          icon: const Icon(FIcons.x),
          semanticLabel: context.t('connectCancel'),
          onTap: _busy ? null : _notNow,
        ),
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: LnSpace.xl),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: LnSpace.md),
                Center(
                  child: Image.asset(
                    'assets/brand/logo.png',
                    width: 64,
                    height: 64,
                    excludeFromSemantics: true,
                  ),
                ),
                const SizedBox(height: LnSpace.xl),
                if (server == null)
                  AuthNotice(text: context.t('connectInvalid'))
                else ...[
                  Text(
                    context.t('connectAsk'),
                    style: ln.text.title.copyWith(color: c.fg),
                  ),
                  const SizedBox(height: LnSpace.md),
                  Container(
                    padding: const EdgeInsetsDirectional.fromSTEB(
                      14,
                      14,
                      14,
                      14,
                    ),
                    decoration: BoxDecoration(
                      color: c.fill2,
                      borderRadius: const BorderRadius.all(
                        Radius.circular(LnRadius.field),
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(FIcons.server, size: 20, color: c.fgMuted),
                        const SizedBox(width: LnSpace.sm),
                        Expanded(
                          child: SelectableText(
                            ltr(serverHost(server)),
                            style: ln.text.headline.copyWith(color: c.fg),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: LnSpace.md),
                  Text(
                    context.t('connectHint'),
                    style: ln.text.caption.copyWith(color: c.fgMuted),
                  ),
                  if (revokes) ...[
                    const SizedBox(height: LnSpace.md),
                    AuthNotice(
                      text: context.t('changeServerHint'),
                      kind: AuthNoticeKind.info,
                    ),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: LnSpace.md),
                    AuthNotice(text: _error!),
                  ],
                  const SizedBox(height: LnSpace.xl),
                  BlockButton(
                    label: context.t(_busy ? 'connecting' : 'connectConfirm'),
                    loading: _busy,
                    onPressed: _busy ? null : () => _connect(server),
                  ),
                ],
                const SizedBox(height: LnSpace.sm),
                BlockButton(
                  label: context.t('connectCancel'),
                  variant: BlockButtonVariant.secondary,
                  onPressed: _busy ? null : _notNow,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
