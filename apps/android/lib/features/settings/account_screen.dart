// Account, built from forui tile groups: the owner's initial, then the identity rows.
// Lonora's counterparts of apps/mobile/app/(settings)/account.tsx and the Web's profile form:
// email, the owner's name and form of address and reply language, and the time zone quiet
// hours follow (the Web owner form's zone, `reach_me.timezone`) (`PUT /owner/preferences`,
// only the fields sent change), the server and this session's end, the passkey devices
// (read-only: registering one needs Credential Manager and the server's assetlinks, which name
// the Expo app only), and sign-out. Lonora has no password change, session list or account
// deletion route, so none is offered. No secret is ever shown.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons, FTileGroup;
import 'package:go_router/go_router.dart';

import '../../app/routes.dart';
import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/actions/session_actions.dart';
import '../../state/app_state.dart';
import '../auth/server_check.dart';
import '../me/me_data.dart';
import '../me/me_screen.dart' show OwnerInitialAvatar, confirmSignOut;
import 'settings_common.dart';
import 'settings_core_data.dart';

class AccountScreen extends StatefulWidget {
  const AccountScreen({super.key});

  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  OwnerProfileData? _profile;
  Object? _error;
  DateTime? _sessionEnds;
  bool _saving = false;
  bool _signingOut = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    unawaited(_readSessionEnd());
  }

  Future<void> _load() async {
    try {
      final profile = await fetchOwnerProfile();
      if (mounted) {
        setState(() {
          _profile = profile;
          _error = null;
        });
      }
    } on SessionRequestCancelled {
      return;
    } catch (e) {
      if (!mounted) return;
      // A failed refresh keeps what is shown and says why.
      if (_profile != null) {
        showErrorToast(context, e);
      } else {
        setState(() => _error = e);
      }
    }
  }

  Future<void> _readSessionEnd() async {
    try {
      final stored = await secureStore.readSession();
      if (mounted) setState(() => _sessionEnds = stored?.expiresAt);
    } catch (_) {
      // Unknown expiry: the row is left out.
    }
  }

  Future<void> _save(Json body) async {
    if (_saving || !mounted) return;
    setState(() => _saving = true);
    try {
      final profile = await saveOwnerPreferences(body);
      if (!mounted) return;
      setState(() => _profile = profile);
      LnToast.show(
        context,
        ownerProfileLabel('saved', context.l10n.lang),
        kind: LnToastKind.positive,
      );
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _editText(String field, String? current) async {
    final label = preferenceFieldLabel(field, context.l10n.lang) ?? field;
    final value = await showLnSheet<String>(
      context,
      title: label,
      builder: (sheet) => _TextEditSheet(initial: current ?? ''),
    );
    if (value == null || value == (current ?? '')) return;
    await _save({field: value.isEmpty ? null : value});
  }

  /// The zone quiet hours are read in: this phone's, the stored one, or another IANA name the
  /// owner types (the server refuses an unknown one with `invalid_timezone`).
  Future<void> _editTimeZone(OwnerProfileData profile) async {
    final title = preferenceFieldLabel('timezone', context.l10n.lang)!;
    final phone = await deviceTimeZone();
    if (!mounted) return;
    final current = profile.timeZone;
    const other = '';
    final chosen = await showLnSheet<String>(
      context,
      title: title,
      builder: (sheet) => FTileGroup(
        children: [
          for (final zone in {?phone, current})
            ChoiceTile(
              title: ltr(zone),
              subtitle: zone == phone ? sheet.t('set_phoneZone') : null,
              selected: zone == current,
              onSelect: () => Navigator.of(sheet).pop(zone),
            ),
          ChoiceTile(
            title: sheet.t('set_otherZone'),
            selected: false,
            onSelect: () => Navigator.of(sheet).pop(other),
          ),
        ],
      ),
    );
    if (!mounted || chosen == null) return;
    var zone = chosen;
    if (zone == other) {
      final typed = await showLnSheet<String>(
        context,
        title: title,
        builder: (sheet) => _TextEditSheet(
          initial: current,
          hint: 'Asia/Riyadh',
          ltr: true,
          maxLength: 64,
        ),
      );
      if (typed == null || typed.isEmpty) return;
      zone = typed;
    }
    if (zone == current) return;
    await _save({
      'reach_me': reachMeWith(profile.reachMe, {'timezone': zone}),
    });
  }

  Future<void> _editReplyLanguage(String? current) async {
    final lang = context.l10n.lang;
    final selected = current ?? 'auto';
    final options = {...replyLanguages, selected};
    final chosen = await showLnSheet<String>(
      context,
      title: ownerProfileLabel('replyLanguage', lang),
      builder: (sheet) => FTileGroup(
        children: [
          for (final option in options)
            ChoiceTile(
              title: replyLanguageLabel(option, lang),
              selected: option == selected,
              onSelect: () => Navigator.of(sheet).pop(option),
            ),
        ],
      ),
    );
    if (chosen == null || chosen == selected) return;
    await _save({'reply_language': chosen == 'auto' ? null : chosen});
  }

  /// Revoking can wait up to 8 s offline: the row stays disabled meanwhile.
  Future<void> _signOut() async {
    if (_signingOut) return;
    setState(() => _signingOut = true);
    try {
      if (await confirmSignOut(context) && mounted) {
        await context.dispatchAndWait(SignOutAction());
      }
    } finally {
      if (mounted) setState(() => _signingOut = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureCoreSettingsStrings(context);
    final lang = context.l10n.lang;
    final owner = context.select((AppState s) => s.session.owner);
    final server = context.select((AppState s) => s.session.server);
    final profile = _profile;
    final notSet = ownerProfileLabel('notSet', lang);
    final loading = profile == null && _error == null;
    // Unknown (loading or unreadable) shows no value, never «Not set».
    String? valueOr(String? v) => profile == null ? null : (v ?? notSet);

    return SettingsPageScaffold(
      title: context.t('account'),
      onRefresh: _load,
      children: [
        // The owner's initial, centred above the first group (Lonora has no owner picture to
        // change). No label above the first group: the page title («Account») already names it.
        if (owner != null) ...[
          Center(
            child: OwnerInitialAvatar(
              name: ownerDisplayName(profile, owner),
              size: 64,
            ),
          ),
          const SizedBox(height: LnSpace.xl),
        ],
        // Detail rows carry no icon: the title at the start, the value at the end, a chevron
        // only where the row opens an editor.
        LnSection(
          footer: context.t('set_nameFooter'),
          children: [
            LnListTile(
              title: preferenceFieldLabel('name', lang)!,
              value: valueOr(profile?.name),
              enabled: profile != null && !_saving,
              onTap: () => _editText('name', profile?.name),
            ),
            LnListTile(
              title: preferenceFieldLabel('address', lang)!,
              value: valueOr(profile?.address),
              enabled: profile != null && !_saving,
              onTap: () => _editText('address', profile?.address),
            ),
            LnListTile(
              title: context.t('email'),
              value: owner == null ? null : ltr(owner.email),
            ),
            if (owner != null)
              LnListTile(title: context.t('set_userId'), value: ltr(owner.id)),
          ],
        ),
        if (_error != null && profile == null) ...[
          const SizedBox(height: LnSpace.sm),
          _InlineFailure(error: _error!, onRetry: _load),
        ],
        const SectionGap(),
        LnSection(
          children: [
            LnListTile(
              title: ownerProfileLabel('replyLanguage', lang),
              value: profile == null
                  ? null
                  : replyLanguageLabel(profile.replyLanguage ?? 'auto', lang),
              enabled: profile != null && !_saving,
              onTap: () => _editReplyLanguage(profile?.replyLanguage),
            ),
            LnListTile(
              title: preferenceFieldLabel('timezone', lang)!,
              value: profile == null ? null : ltr(profile.timeZone),
              enabled: profile != null && !_saving,
              onTap: profile == null ? null : () => _editTimeZone(profile),
            ),
          ],
        ),
        const SectionGap(),
        LnSection(
          children: [
            LnListTile(
              title: context.t('server'),
              value: server == null ? null : ltr(serverHost(server)),
              onTap: () => context.push(Routes.server),
            ),
            if (_sessionEnds != null)
              LnListTile(
                title: context.t('set_sessionEnds'),
                value: _sessionEndText(lang, _sessionEnds!),
              ),
          ],
        ),
        // Unreadable devices are not «none»: the section waits for a profile.
        if (profile != null || loading) ...[
          const SectionGap(),
          LnSection(
            title: context.t('set_passkeyDevices'),
            footer: context.t('set_passkeyElsewhere'),
            children: [
              if (profile == null || profile.devices.isEmpty)
                LnListTile(
                  title: profile == null
                      ? context.t('sh_loading')
                      : context.t('set_noPasskeyDevices'),
                )
              else
                for (final device in profile.devices)
                  LnListTile(title: device.name),
            ],
          ),
        ],
        const SectionGap(),
        // Sign-out on a card of its own, as text in the error colour.
        LnSection(
          children: [
            LnListTile(
              title: context.t('logout'),
              destructive: true,
              enabled: !_signingOut,
              onTap: _signOut,
            ),
          ],
        ),
      ],
    );
  }
}

/// «Nov 28 9:30 AM» in the owner's language, the chat list's date and time formats.
String _sessionEndText(String lang, DateTime ends) {
  final local = ends.toLocal();
  return isolate(
    '${formatDate('MMMd', lang, local)} ${formatDate('jm', lang, local)}',
  );
}

/// A compact load failure inside a page that still shows what it knows.
class _InlineFailure extends StatelessWidget {
  const _InlineFailure({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final offline = error is ApiError && (error as ApiError).isNetwork;
    return LnSection(
      children: [
        LnListTile(
          icon: offline ? FIcons.wifiOff : FIcons.triangleAlert,
          title: errorMessage(context, error) ?? context.t('request_failed'),
          value: context.t('retry'),
          onTap: onRetry,
        ),
      ],
    );
  }
}

/// Name / form of address editor (≤ 80 characters, `OwnerPreferencesUpdate`). Saving an empty
/// field clears it.
class _TextEditSheet extends StatefulWidget {
  const _TextEditSheet({
    required this.initial,
    this.hint,
    this.ltr = false,
    this.maxLength = 80,
  });

  final String initial;
  final String? hint;

  /// Identifiers (a time zone) read left to right even in Arabic.
  final bool ltr;
  final int maxLength;

  @override
  State<_TextEditSheet> createState() => _TextEditSheetState();
}

class _TextEditSheetState extends State<_TextEditSheet> {
  late final _controller = TextEditingController(text: widget.initial);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _done() => Navigator.of(context).pop(_controller.text.trim());

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Directionality(
        textDirection: widget.ltr
            ? TextDirection.ltr
            : Directionality.of(context),
        child: LnTextField(
          controller: _controller,
          hint: widget.hint,
          autofocus: true,
          textCapitalization: widget.ltr
              ? TextCapitalization.none
              : TextCapitalization.words,
          keyboardType: widget.ltr ? TextInputType.url : null,
          autocorrect: !widget.ltr,
          textInputAction: TextInputAction.done,
          inputFormatters: [
            LengthLimitingTextInputFormatter(widget.maxLength),
            FilteringTextInputFormatter.deny(RegExp(r'[\n\r]')),
          ],
          onSubmitted: (_) => _done(),
        ),
      ),
      const SizedBox(height: LnSpace.md),
      BlockButton(label: context.t('save'), onPressed: _done),
      const SizedBox(height: LnSpace.xs),
      BlockButton(
        label: context.t('sh_cancel'),
        variant: BlockButtonVariant.secondary,
        onPressed: () => Navigator.of(context).pop(),
      ),
    ],
  );
}
