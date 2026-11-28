// Sign-in and first-run owner setup: kit fields and buttons only, no illustration. Behaviour and
// wording follow apps/mobile/app/sign-in.tsx: the server is asked `GET /onboarding` first; a server
// without an owner shows the setup form (setup token from the server configuration or a connect
// link). Under the sign-in form, «ما عندك حساب؟ سجّل من lonora.io» opens Lonora Cloud's sign-up
// in the browser (a Lonora Cloud server's owner is the website account).
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/material.dart' show Scaffold;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/prefs_actions.dart';
import '../../state/actions/session_actions.dart';
import '../../state/app_state.dart';
import '../settings/settings_common.dart';
import 'auth_widgets.dart';
import 'server_check.dart';

class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key});

  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

/// What `GET /onboarding` answered for one address.
typedef _Checked = ({String server, bool initialized});

class _SignInScreenState extends State<SignInScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _token = TextEditingController();
  final _passwordFocus = FocusNode();

  _Checked? _checked;
  String? _probing;
  Timer? _debounce;
  bool _busy = false;
  String? _error;
  bool _redirected = false;
  bool _tokenFilled = false;

  /// The server the form was last built for: another one empties the setup token.
  String? _formServer;

  @override
  void initState() {
    super.initState();
    final session = context.read().session;
    _email.text = session.lastEmail ?? '';
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _email.dispose();
    _password.dispose();
    _token.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  /// Asks the server whether it has its owner (400 ms after the address settles, as Expo).
  /// An unreachable server counts as "has an owner": sign-in's own error then says why.
  void _probe(String server, {bool immediately = false}) {
    if (_probing == server && !immediately) return;
    _probing = server;
    _debounce?.cancel();
    _debounce = Timer(
      immediately ? Duration.zero : const Duration(milliseconds: 400),
      () async {
        bool initialized;
        try {
          initialized = await probeOwnerInitialized(server)
              .timeout(const Duration(milliseconds: 10400));
        } catch (_) {
          final known = _checked;
          initialized = known != null && known.server == server
              ? known.initialized
              : true;
        }
        if (!mounted || _probing != server) return;
        setState(() => _checked = (server: server, initialized: initialized));
      },
    );
  }

  bool _pending(String server) => _checked?.server != server;

  bool _setup(String server) =>
      !_pending(server) && _checked?.initialized == false;

  bool _blocked(String server) {
    final setup = _setup(server);
    return _busy ||
        _pending(server) ||
        _email.text.trim().isEmpty ||
        _password.text.isEmpty ||
        (setup && (_password.text.length < 12 || _token.text.isEmpty));
  }

  Future<void> _submit(String server) async {
    if (_blocked(server)) return;
    final setup = _setup(server);
    // The server's setup token is 24 characters at least: a shorter one was cut short.
    if (setup && _token.text.trim().length < 24) {
      setState(() => _error = context.t('setupTokenShort'));
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() {
      _busy = true;
      _error = null;
    });
    final email = _email.text.trim();
    final password = _password.text;
    try {
      if (setup) {
        await context.dispatchAndWait(
          SetupOwnerAction(
            server: server,
            email: email,
            password: password,
            bootstrapToken: _token.text.trim(),
          ),
        );
      } else {
        await context.dispatchAndWait(
          SignInAction(server: server, email: email, password: password),
        );
      }
      // Signed in: the router leaves this screen. Secrets never stay in memory.
      if (mounted) {
        _password.clear();
        _token.clear();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = errorMessage(context, e));
      // An owner created elsewhere meanwhile (or a server that was unreachable) is asked again.
      _probe(server, immediately: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    final session = context.select((AppState s) => s.session);
    final locale = context.select((AppState s) => s.prefs.locale);
    final linked = session.pendingSetupToken;
    // The server the owner chose last (a connect link sets it too); a link's token is only
    // ever used for the server it was issued for.
    final server = session.lastServer ?? linked?.server;

    if (server == null || server.isEmpty) {
      // No server yet: the first step is choosing it.
      if (!_redirected) {
        _redirected = true;
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) context.go(Routes.server);
        });
      }
      return Scaffold(backgroundColor: c.bg);
    }
    _probe(server);
    final pending = _pending(server);
    final setup = _setup(server);
    // The setup token belongs to one server and to the setup form: a server change, or the
    // server answering that it has its owner, empties it (apps/mobile/app/sign-in.tsx:70-71).
    if (_formServer != server || (!pending && !setup)) {
      _formServer = server;
      _tokenFilled = false;
      if (_token.text.isNotEmpty) _token.clear();
    }
    // A connect link's setup token fills the setup form, only for the server it was issued for.
    if (setup &&
        !_tokenFilled &&
        linked != null &&
        sameServer(linked.server, server)) {
      _tokenFilled = true;
      _token.text = linked.token;
    }
    final blocked = _blocked(server);

    return Scaffold(
      backgroundColor: c.bg,
      body: Column(
        children: [
          ScreenHeader(
            trailing: _LanguageChip(
              label: locale == 'ar' ? 'English' : 'العربية',
              onTap: () => context.dispatch(
                SetLocaleAction(locale == 'ar' ? 'en' : 'ar'),
              ),
            ),
          ),
          Expanded(
            child: AutofillGroup(
              child: ListView(
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                padding: EdgeInsetsDirectional.fromSTEB(
                  LnSpace.xl,
                  LnSpace.md,
                  LnSpace.xl,
                  LnSpace.xxl + MediaQuery.paddingOf(context).bottom,
                ),
                children: [
                  Center(
                    child: Image.asset(
                      'assets/brand/logo.png',
                      width: 64,
                      height: 64,
                      excludeFromSemantics: true,
                    ),
                  ),
                  const SizedBox(height: LnSpace.xl),
                  Semantics(
                    header: true,
                    child: Text(
                      context.t(setup ? 'setupTitle' : 'signIn'),
                      style: ln.text.largeTitle.copyWith(color: c.fg),
                    ),
                  ),
                  const SizedBox(height: LnSpace.xs),
                  Text(
                    context.t(setup ? 'setupHint' : 'serverHint'),
                    style: ln.text.caption.copyWith(color: c.fgMuted),
                  ),
                  const SizedBox(height: LnSpace.lg),
                  if (session.expired) ...[
                    AuthNotice(
                      text: context.t('auth_sessionEnded'),
                      kind: AuthNoticeKind.info,
                    ),
                    const SizedBox(height: LnSpace.md),
                  ],
                  _ServerRow(server: server, pending: pending),
                  const SizedBox(height: LnSpace.md),
                  LtrField(
                    label: context.t('email'),
                    child: LnTextField(
                      controller: _email,
                      enabled: !_busy,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [
                        AutofillHints.email,
                        AutofillHints.username,
                      ],
                      onChanged: (_) => setState(() {}),
                      onSubmitted: (_) => _passwordFocus.requestFocus(),
                    ),
                  ),
                  const SizedBox(height: LnSpace.md),
                  SecretField(
                    controller: _password,
                    focusNode: _passwordFocus,
                    label: context.t(setup ? 'setupPassword' : 'password'),
                    enabled: !_busy,
                    // Laid out as the email box above it, so both texts start together.
                    ltr: true,
                    autofillHints: [
                      setup
                          ? AutofillHints.newPassword
                          : AutofillHints.password,
                    ],
                    textInputAction: setup
                        ? TextInputAction.next
                        : TextInputAction.done,
                    onChanged: (_) => setState(() {}),
                    onSubmitted: setup ? null : (_) => _submit(server),
                  ),
                  if (setup) ...[
                    const SizedBox(height: LnSpace.md),
                    SecretField(
                      controller: _token,
                      label: context.t('setupToken'),
                      enabled: !_busy,
                      ltr: true,
                      // A server secret, often filled from a link: never shown (Expo).
                      revealable: false,
                      textInputAction: TextInputAction.done,
                      onChanged: (_) => setState(() {}),
                      onSubmitted: (_) => _submit(server),
                    ),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: LnSpace.md),
                    AuthNotice(text: _error!),
                  ],
                  const SizedBox(height: LnSpace.xl),
                  BlockButton(
                    label: context.t(
                      _busy ? 'connecting' : (setup ? 'setupCreate' : 'signIn'),
                    ),
                    loading: _busy,
                    onPressed: blocked ? null : () => _submit(server),
                  ),
                  // Once the server has answered: one still without its owner creates it here
                  // instead, and the line would flash before the setup form.
                  if (!pending && !setup) ...[
                    const SizedBox(height: LnSpace.sm),
                    const _SignUpLink(),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// «ما عندك حساب؟ سجّل من lonora.io»: Lonora Cloud's sign-up page, outside the app. Read as one
/// link (not a button) with its address, in a 48 dp row; one tap opens one browser.
class _SignUpLink extends StatefulWidget {
  const _SignUpLink();

  static final url = Uri.parse('https://lonora.io/#start');

  @override
  State<_SignUpLink> createState() => _SignUpLinkState();
}

class _SignUpLinkState extends State<_SignUpLink> {
  bool _opening = false;

  Future<void> _open() async {
    if (_opening) return;
    _opening = true;
    try {
      await openExternalUrl(context, _SignUpLink.url);
    } finally {
      _opening = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final question = context.t('auth_noAccount');
    final action = context.t('auth_signUpAt');
    return Semantics(
      link: true,
      linkUrl: _SignUpLink.url,
      label: '$question $action',
      onTap: _open,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: _open,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: LnSize.minTouch),
          child: Center(
            child: Text.rich(
              TextSpan(
                children: [
                  TextSpan(text: '$question '),
                  TextSpan(
                    text: action,
                    style: ln.text.captionStrong.copyWith(color: c.link),
                  ),
                ],
              ),
              textAlign: TextAlign.center,
              style: ln.text.caption.copyWith(color: c.fgMuted),
            ),
          ),
        ),
      ),
    );
  }
}

/// The language switch of the signed-out screens (Expo's «English» / «العربية» button): a
/// 36 dp stadium in a 48 dp touch target, the language named in its own script.
class _LanguageChip extends StatelessWidget {
  const _LanguageChip({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      haptic: true,
      semanticLabel: label,
      semanticHint: context.t('auth_switchLanguage'),
      // ExcludeSemantics, not excludeChildSemantics: that would drop the tap action.
      child: ExcludeSemantics(
        child: SizedBox(
          height: 48,
          child: Center(
            child: Container(
              height: 36,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              alignment: Alignment.center,
              decoration: ShapeDecoration(
                color: c.fill3,
                shape: const StadiumBorder(),
              ),
              child: Text(
                label,
                style: ln.text.captionStrong.copyWith(color: c.fg),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The remembered server, with the way to change it (the server step).
class _ServerRow extends StatelessWidget {
  const _ServerRow({required this.server, required this.pending});

  final String server;
  final bool pending;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: () => context.push(Routes.server),
      semanticLabel: '${context.t('server')}: ${serverHost(server)}',
      semanticHint: context.t('auth_change'),
      // ExcludeSemantics, not excludeChildSemantics: that would drop the tap action.
      child: ExcludeSemantics(
        child: Container(
          constraints: const BoxConstraints(minHeight: 56),
          padding: const EdgeInsetsDirectional.fromSTEB(14, 8, 14, 8),
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
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      pending
                          ? context.t('auth_checking')
                          : context.t('server'),
                      style: ln.text.small.copyWith(color: c.fgMuted),
                    ),
                    Text(
                      ltr(serverHost(server)),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: ln.text.captionStrong.copyWith(color: c.fg),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: LnSpace.xs),
              if (pending)
                const LnSpinner(size: 16)
              else
                Text(
                  context.t('auth_change'),
                  style: ln.text.captionStrong.copyWith(color: c.link),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
