// «مزوّدو النماذج» and a provider's key, built from the kit: tile groups, the write-only secret
// field and block buttons. Lonora's counterparts of apps/web ConnectionPages.tsx `ProvidersPage`,
// `ChatGptPlanRow` and `ProviderForm`: a key is tested (nothing stored) and saved encrypted; it is
// never shown, logged or read back. Lonora has no route that removes a provider key, so none is
// offered; a new key replaces the old one.
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../core/api/api_error.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../settings_common.dart';
import 'ext_common.dart';
import 'integrations_data.dart';

/// The providers that take a key, with whether one is stored, and the ChatGPT plan's sign-in.
class ProvidersPage extends StatefulWidget {
  const ProvidersPage({super.key});

  @override
  State<ProvidersPage> createState() => _ProvidersPageState();
}

class _ProvidersPageState extends State<ProvidersPage> {
  List<ProviderStatus>? _providers;
  Object? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final list = await fetchProviders();
      if (mounted) {
        setState(() {
          _providers = list;
          _error = null;
        });
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (!mounted) return;
      // A failed refresh keeps the list on screen and says so.
      if (_providers != null) {
        showErrorToast(context, e);
      } else {
        setState(() => _error = e);
      }
    }
  }

  Future<void> _open(ProviderStatus provider) async {
    final saved = await pushSettingsPage<bool>(
      context,
      ProviderKeyPage(provider: provider.id, configured: provider.configured),
    );
    if (saved != true || !mounted) return;
    LnToast.show(context, context.t('ix_saved'), kind: LnToastKind.positive);
    await _load();
  }

  Future<void> _signOut() async {
    final lang = context.l10n.lang;
    final text = chatgptText(lang);
    final ok = await showLnConfirm(
      context,
      title: context.t('ix_signOutChatGptQ'),
      confirmLabel: text.signOut,
      cancelLabel: context.t('sh_cancel'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      final result = await signOutChatGpt();
      if (!mounted) return;
      LnToast.show(
        context,
        signOutLine(result, lang),
        kind: asRevoked(result) ? LnToastKind.positive : LnToastKind.notice,
      );
      await _load();
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  static bool asRevoked(Map<String, Object?> result) =>
      result['revoked'] == true;

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final lang = context.l10n.lang;
    final providers = _providers;
    if (providers == null) {
      return SettingsPageScaffold(
        title: context.t('ix_modelProviders'),
        body: _error == null
            ? const PageLoading(groups: [5])
            : LoadFailure(error: _error!, onRetry: _load),
      );
    }
    final plan = providers.where((p) => !p.takesKey).firstOrNull;
    final planRow = plan == null ? null : chatgptRow(plan.signIn, lang);
    final keyed = providers.where((p) => p.takesKey).toList();
    final text = chatgptText(lang);
    final email = plan?.signIn?['email'];
    return SettingsPageScaffold(
      title: context.t('ix_modelProviders'),
      onRefresh: _load,
      children: [
        if (planRow != null) ...[
          LnSection(
            children: [
              WrapTile(
                icon: FIcons.cpu,
                title: text.name,
                subtitle: [
                  planRow.line,
                  if (email is String && email.isNotEmpty) ltr(email),
                ].join(dotSeparator),
              ),
              LnListTile(
                icon: FIcons.externalLink,
                title: text.manageUsage,
                // Opens the browser: no forward chevron.
                showChevron: false,
                onTap: () =>
                    openExternalUrl(context, Uri.parse(manageUsageUrl)),
              ),
              if (planRow.signOut)
                LnListTile(
                  icon: LnIcons.logOut,
                  title: text.signOut,
                  destructive: true,
                  enabled: !_busy,
                  onTap: _signOut,
                ),
            ],
          ),
          const SectionGap(),
        ],
        LnSection(
          title: context.t('ix_modelProviders'),
          footer: context.t('ix_catalogNote'),
          children: [
            for (final p in keyed)
              WrapTile(
                icon: FIcons.cpu,
                title: providerName(p.id),
                subtitle: p.configured ? context.t('ix_keySaved') : null,
                trailing: _StatusTrailing(configured: p.configured),
                onTap: () => _open(p),
              ),
          ],
        ),
      ],
    );
  }
}

class _StatusTrailing extends StatelessWidget {
  const _StatusTrailing({required this.configured});

  final bool configured;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      StatusChip(
        label: context.t(configured ? 'configured' : 'notConfigured'),
        kind: configured ? StatusChipKind.success : StatusChipKind.neutral,
        icon: configured ? FIcons.check : null,
      ),
      const SizedBox(width: LnSpace.xxs),
      Icon(FIcons.chevronRight, color: context.ln.colors.chevron),
    ],
  );
}

/// One provider's key: write-only field, «Test the connection», «Save the key». Pops `true`
/// once a key is saved.
class ProviderKeyPage extends StatefulWidget {
  const ProviderKeyPage({
    super.key,
    required this.provider,
    required this.configured,
  });

  final String provider;
  final bool configured;

  @override
  State<ProviderKeyPage> createState() => _ProviderKeyPageState();
}

class _ProviderKeyPageState extends State<ProviderKeyPage> {
  final _key = TextEditingController();
  ({bool ok, String text})? _test;
  FormAction? _running;

  bool get _busy => _running != null;

  @override
  void dispose() {
    _key
      ..clear()
      ..dispose();
    super.dispose();
  }

  String? _valid() {
    final key = _key.text.trim();
    if (key.length < 8) {
      LnToast.show(context, context.t('ix_enterKey'), kind: LnToastKind.notice);
      return null;
    }
    return key;
  }

  Future<void> _runTest() async {
    final key = _valid();
    if (key == null || _busy) return;
    setState(() {
      _running = FormAction.test;
      _test = null;
    });
    try {
      await testProviderKey(widget.provider, key);
      if (mounted) {
        setState(
          () => _test = (ok: true, text: context.t('ix_connectionWorks')),
        );
      }
    } catch (e) {
      final text = mounted ? errorMessage(context, e) : null;
      if (mounted && text != null) {
        setState(() => _test = (ok: false, text: text));
      }
    } finally {
      if (mounted) setState(() => _running = null);
    }
  }

  Future<void> _save() async {
    final key = _valid();
    if (key == null || _busy) return;
    setState(() => _running = FormAction.save);
    try {
      await saveProviderKey(widget.provider, key);
      _key.clear();
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _running = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final test = _test;
    return SettingsPageScaffold(
      title: providerName(widget.provider),
      children: [
        Gutter(
          bottom: LnSpace.lg,
          child: widget.configured
              ? MaskedSecret(caption: context.t('ix_credentialConfigured'))
              : Text(
                  context.t('ix_addCredential'),
                  style: context.ln.text.body.copyWith(
                    color: context.ln.colors.fgMuted,
                  ),
                ),
        ),
        Gutter(
          bottom: LnSpace.md,
          child: SecretField(
            controller: _key,
            label: context.t('ix_apiKey'),
            helper: context.t('ix_keyEncrypted'),
            enabled: !_busy,
          ),
        ),
        if (test != null)
          Gutter(
            bottom: LnSpace.md,
            child: TestResultLine(ok: test.ok, text: test.text),
          ),
        Gutter(
          bottom: LnSpace.sm,
          child: BlockButton(
            label: context.t('ix_testConnection'),
            variant: BlockButtonVariant.secondary,
            loading: _running == FormAction.test,
            onPressed: _busy ? null : _runTest,
          ),
        ),
        Gutter(
          bottom: LnSpace.lg,
          child: BlockButton(
            label: context.t('ix_saveKey'),
            loading: _running == FormAction.save,
            onPressed: _busy ? null : _save,
          ),
        ),
        SettingsNote(
          context.t(widget.configured ? 'ix_replaceKeyNote' : 'ix_catalogNote'),
        ),
      ],
    );
  }
}
