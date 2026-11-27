// The owner action card (permission card), drawn like the other fixed cards: the flat header
// band (agent ••• shield), the shared spec's title, facts and hint (ported
// packages/core/src/owner-actions.ts, the same words as Web and Expo), and its buttons; once
// settled, the disabled stadium with the past state and the settled line. Every button is
// one explicit owner tap on this card's own owner-session route
// (apps/mobile/components/owner-action-card.tsx). Secret values go only to the card's route
// and are cleared at once; they never ride on an action or into the store, and nothing is
// echoed or logged.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/services.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../../state/actions/base.dart';
import '../../state/app_state.dart';
import 'card_parts.dart';
import 'cards_actions.dart';
import 'cards_strings.dart';

/// Asks the conversation to show another timeline card ("Show the latest" on a replaced
/// card). [key] is a [TimelineCard.key], e.g. `owner_action:<id>`.
class TimelineCardJumpNotification extends Notification {
  const TimelineCardJumpNotification(this.key);
  final String key;
}

class OwnerActionCardView extends StatelessWidget {
  const OwnerActionCardView({
    super.key,
    required this.threadId,
    required this.cardId,
    this.width,
  });

  final String threadId;
  final String cardId;
  final double? width;

  @override
  Widget build(BuildContext context) {
    final row = context.select(
      (AppState s) => sideList(
        s.thread(threadId),
        SideKeys.ownerActions,
      ).where((r) => asStr(r['id']) == cardId).firstOrNull,
    );
    if (row == null) return const SizedBox.shrink();
    return OwnerActionCard(
      key: ValueKey(cardId),
      threadId: threadId,
      row: row,
      width: width,
    );
  }
}

/// One owner action card for [row] (the server's `OwnerAction` JSON).
class OwnerActionCard extends StatefulWidget {
  const OwnerActionCard({
    super.key,
    required this.threadId,
    required this.row,
    this.width,
    this.now,
  });

  final String threadId;
  final Json row;
  final double? width;

  /// The clock the spec reads times against (tests pin it).
  final DateTime? now;

  @override
  State<OwnerActionCard> createState() => _OwnerActionCardState();
}

class _OwnerActionCardState extends State<OwnerActionCard> {
  bool _busy = false;
  String? _pressed;
  String? _error;
  final Map<String, TextEditingController> _values = {};
  final TextEditingController _address = TextEditingController();
  bool _signingIn = false;
  String? _account;

  Json get _row => widget.row;
  String get _id => asStr(_row['id']);

  @override
  void didUpdateWidget(OwnerActionCard old) {
    super.didUpdateWidget(old);
    // Typed values never outlive the form: Not now, or a save elsewhere, clears them.
    if (_row['status'] != 'pending') _clearTyped();
  }

  void _clearTyped() {
    for (final c in _values.values) {
      c.clear();
    }
    _address.clear();
  }

  @override
  void dispose() {
    for (final c in _values.values) {
      c.dispose();
    }
    _address.dispose();
    super.dispose();
  }

  TextEditingController _field(String key) =>
      _values[key] ??= TextEditingController();

  /// One tap's task. A refusal reads in the owner's words; a card that changed elsewhere
  /// (`owner_action_card_changed`, a conflict) is read again first, whatever the task
  /// (owner-action-card.tsx `run`).
  Future<void> _run(String key, Future<void> Function() task) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _pressed = key;
      _error = null;
    });
    try {
      await task();
    } on ApiError catch (e) {
      if (!mounted) return;
      if (e.code == ownerActionChanged || e.isConflict) {
        await context.dispatchAndWait(
          RereadOwnerActionsAction(widget.threadId),
        );
      }
      if (mounted) setState(() => _error = context.l10n.errorText(e.code));
    } on SessionRequestCancelled {
      // Signed out.
    } catch (_) {
      if (mounted) {
        setState(() => _error = context.l10n.errorText('request_failed'));
      }
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _pressed = null;
        });
      }
    }
  }

  Future<void> _decide(OwnerActionButton button) => _run(button.key, () async {
    unawaited(HapticFeedback.selectionClick());
    final action = OwnerActionDecisionAction(
      threadId: widget.threadId,
      cardId: _id,
      decision: button.decision,
      outcome: button.outcome,
      tradingMode: button.tradingMode,
    );
    await context.dispatchAndWait(action);
    final updated = action.updated;
    final applied = asString(asJson(updated?['result'])['trading_mode']);
    if (button.tradingMode == null || applied == null || !mounted) return;
    // The switch the server applied, and the approvals it withdrew (web OwnerActionCard).
    final locale = context.l10n.lang;
    final name =
        asString(asJson(asJson(updated!['facts'])['agent'])['name']) ??
        asString(asJson(asJson(_row['facts'])['agent'])['name']) ??
        '';
    final withdrawn = asJson(updated['result'])['withdrawn'];
    try {
      LnToast.show(
        context,
        modeChangeLine(
          name,
          applied == 'full' ? 'full' : 'ask',
          withdrawn is num ? withdrawn : 0,
          locale,
        ),
        kind: LnToastKind.positive,
      );
    } catch (_) {
      // No toaster above this card (previews).
    }
  });

  /// The values go only to the card's own route, which stores them encrypted. They never
  /// ride on an action or into the store (a refused action stays reachable there); the
  /// fields are cleared before the request and only the answered row is dispatched.
  Future<void> _save(SecretForm form) => _run('save', () async {
    // An optional field left empty is not sent.
    final sent = <String, String>{
      for (final field in form.fields)
        if (_field(field.key).text.trim().isNotEmpty)
          field.key: _field(field.key).text,
    };
    _clearTyped();
    final Object? row;
    try {
      row = await api.post('/owner-actions/$_id/secret', {'values': sent});
    } finally {
      sent.clear();
    }
    if (mounted) {
      context.dispatch(PatchOwnerActionAction(widget.threadId, asJson(row)));
    }
  });

  Future<void> _continue({bool newAccount = false}) =>
      _run(newAccount ? 'other' : 'continue', () async {
        final action = ChatGptStartAction(cardId: _id, newAccount: newAccount);
        await context.dispatchAndWait(action);
        final url = action.authorizationUrl;
        final uri = url == null ? null : Uri.tryParse(url);
        // The address field appears only once the sign-in page actually opened.
        final opened =
            uri != null &&
            (uri.scheme == 'https' || uri.scheme == 'http') &&
            await launchUrl(uri, mode: LaunchMode.externalApplication);
        if (!mounted) return;
        if (!opened) {
          setState(() => _error = context.l10n.errorText('request_failed'));
          return;
        }
        setState(() {
          _signingIn = true;
          _account = action.account;
        });
      });

  /// The address the browser landed on goes only to the card's own route
  /// (`POST /owner-actions/{id}/chatgpt/finish {address}`, trimmed as chatgpt-plan.ts
  /// `finishChatGptSignIn` sends it); the field is cleared first and only the answered row
  /// is dispatched.
  Future<void> _finish() => _run('finish', () async {
    final sent = _address.text.trim();
    _address.clear();
    final row = await api.post('/owner-actions/$_id/chatgpt/finish', {
      'address': sent,
    });
    if (mounted) {
      context.dispatch(PatchOwnerActionAction(widget.threadId, asJson(row)));
    }
  });

  Future<void> _renew() => _run('renew', () async {
    await context.dispatchAndWait(
      OwnerActionRenewAction(threadId: widget.threadId, cardId: _id),
    );
  });

  @override
  Widget build(BuildContext context) {
    registerCardsStrings(context.l10n);
    final ln = context.ln;
    final c = ln.colors;
    final locale = context.l10n.lang;
    final text = ownerActionText(locale);
    final spec = ownerActionCard(_row, locale, widget.now ?? DateTime.now());
    final live = ownerActionLive(_row);
    final supersededBy = asString(_row['superseded_by']);
    final form = spec.secret;
    final signIn = spec.signIn;

    BlockButton button(OwnerActionButton b) => BlockButton(
      label: b.label,
      variant: b.primary
          ? BlockButtonVariant.primary
          : BlockButtonVariant.secondary,
      loading: _pressed == b.key,
      onPressed: _busy || (b.decision == 'confirm' && spec.passkey)
          ? null
          : () => _decide(b),
    );

    final actions = <Widget>[];
    if (form != null) {
      final ready = !form.fields.any(
        (f) => f.required && _field(f.key).text.trim().isEmpty,
      );
      actions.add(
        ButtonPair(
          first: BlockButton(
            label: text.notNow,
            variant: BlockButtonVariant.secondary,
            loading: _pressed == 'cancel',
            onPressed: _busy
                ? null
                : () => _decide(
                    spec.buttons.firstWhere((b) => b.key == 'cancel'),
                  ),
          ),
          second: BlockButton(
            label: form.submit,
            loading: _pressed == 'save',
            onPressed: _busy || !ready ? null : () => _save(form),
          ),
        ),
      );
    } else if (spec.buttons.length == 2 &&
        spec.buttons.any((b) => b.decision == 'cancel')) {
      // Deny / Allow: the cancel on the reading start, the confirm on the end.
      final cancel = spec.buttons.firstWhere((b) => b.decision == 'cancel');
      final confirm = spec.buttons.firstWhere((b) => b.decision != 'cancel');
      actions.add(ButtonPair(first: button(cancel), second: button(confirm)));
    } else {
      actions.addAll(spec.buttons.map(button));
    }
    if (!live && spec.buttons.isEmpty) {
      // The consumed state: the disabled stadium with the past state.
      actions.add(
        BlockButton(
          label: ownerActionStatus(_row, locale),
          variant: BlockButtonVariant.done,
        ),
      );
    }
    if (supersededBy != null) {
      actions.add(
        BlockButton(
          label: text.latest,
          variant: BlockButtonVariant.secondary,
          onPressed: () =>
              TimelineCardJumpNotification('owner_action:$supersededBy')
                  .dispatch(context),
        ),
      );
    } else if (_row['status'] == 'expired' &&
        _row['kind'] == 'settle_operation') {
      actions.add(
        BlockButton(
          label: text.renew,
          variant: BlockButtonVariant.secondary,
          loading: _pressed == 'renew',
          onPressed: _busy ? null : _renew,
        ),
      );
    }

    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        CardKicker(text: spec.title),
        for (var i = 0; i < spec.lines.length; i++)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(
              spec.lines[i],
              textDirection: textDirectionFor(
                spec.lines[i],
                Directionality.of(context),
              ),
              style: i == 0
                  ? ln.text.title.copyWith(color: c.fg)
                  : ln.text.caption.copyWith(color: c.fg),
            ),
          ),
        if (spec.hint != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              spec.hint!,
              style: ln.text.footnote.copyWith(color: c.fgMuted),
            ),
          ),
        if (form != null)
          for (final field in form.fields)
            Padding(
              padding: const EdgeInsets.only(top: LnSpace.sm),
              child: Directionality(
                textDirection: TextDirection.ltr,
                child: LnTextField(
                  controller: _field(field.key),
                  label: field.label,
                  obscureText: field.type == 'password',
                  enabled: !_busy,
                  keyboardType: field.type == 'url'
                      ? TextInputType.url
                      : TextInputType.visiblePassword,
                  // Never offered to, or filled from, the system's password store.
                  autofillHints: const [],
                  onChanged: (_) => setState(() {}),
                ),
              ),
            ),
        if (signIn != null) ...[
          const SizedBox(height: LnSpace.sm),
          BlockButton(
            label: signIn.continueLabel,
            variant: _signingIn
                ? BlockButtonVariant.secondary
                : BlockButtonVariant.primary,
            loading: _pressed == 'continue',
            onPressed: _busy ? null : () => _continue(),
          ),
          if (_signingIn && continuingAsLine(_account, locale) != null) ...[
            Padding(
              padding: const EdgeInsets.only(top: LnSpace.xs),
              child: Text(
                continuingAsLine(_account, locale)!,
                style: ln.text.footnote.copyWith(color: c.fgMuted),
              ),
            ),
            const SizedBox(height: LnSpace.xs),
            BlockButton(
              label: signIn.otherAccount,
              variant: BlockButtonVariant.secondary,
              loading: _pressed == 'other',
              onPressed: _busy ? null : () => _continue(newAccount: true),
            ),
          ],
          if (_signingIn) ...[
            const SizedBox(height: LnSpace.sm),
            Directionality(
              textDirection: TextDirection.ltr,
              child: LnTextField(
                controller: _address,
                label: signIn.address,
                obscureText: true,
                enabled: !_busy,
                keyboardType: TextInputType.url,
                autofillHints: const [],
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(height: LnSpace.xs),
            BlockButton(
              label: signIn.submit,
              loading: _pressed == 'finish',
              onPressed: _busy || _address.text.trim().isEmpty ? null : _finish,
            ),
          ],
        ],
        if (spec.passkey)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              text.passkeyUnsupported,
              style: ln.text.footnote.copyWith(color: c.fgMuted),
            ),
          ),
        if (spec.outcome != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Semantics(
              liveRegion: true,
              child: Text(
                spec.outcome!,
                style: ln.text.footnote.copyWith(color: c.fgMuted),
              ),
            ),
          ),
        CardError(text: _error),
      ],
    );

    return ActionCard(
      width: widget.width,
      semanticLabel: spec.title,
      header: CardHeaderArt(agentId: asString(_row['agent_id'])),
      body: body,
      actions: actions,
    );
  }
}
