// News domains, RSS feeds and Telegram: the «News and channels» sheets, built from the sheet, tile
// groups and fields. Lonora's counterparts of apps/web IntegrationsPage.tsx `domainsSheet`,
// `rssSheet` and `telegramSheet`. Every removal asks first. Telegram delivers the alerts a push
// carries; what the owner writes there reaches the chosen agent as an owner message and never
// decides a card.
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../core/json.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../settings_common.dart';
import 'ext_common.dart';
import 'integrations_data.dart';

Future<bool> _confirmRemove(BuildContext context, String name) => showLnConfirm(
  context,
  title: context.t('ix_removeQ', [name]),
  confirmLabel: capabilityText(context.l10n.lang).remove,
  cancelLabel: context.t('sh_cancel'),
  destructive: true,
);

/// A sheet's list and its inline «Add» field.
class _AddRow extends StatelessWidget {
  const _AddRow({
    required this.controller,
    required this.label,
    required this.hint,
    required this.busy,
    required this.onAdd,
  });

  final TextEditingController controller;
  final String label;
  final String hint;
  final bool busy;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.end,
    children: [
      Expanded(
        child: LnTextField(
          controller: controller,
          label: label,
          hint: hint,
          enabled: !busy,
          keyboardType: TextInputType.url,
          autocorrect: false,
          textDirection: TextDirection.ltr,
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => onAdd(),
        ),
      ),
      const SizedBox(width: LnSpace.xs),
      BlockButton(
        label: context.t('ix_add'),
        expand: false,
        loading: busy,
        onPressed: busy ? null : onAdd,
      ),
    ],
  );
}

/// «نطاقات الأخبار»: the trusted feed domains, remove (asks) and add. Completes when closed;
/// the caller reloads.
Future<void> showDomainsSheet(BuildContext context, List<Json> domains) =>
    showLnSheet<void>(
      context,
      title: context.t('ix_newsDomains'),
      builder: (_) => _DomainsSheet(initial: domains),
    );

class _DomainsSheet extends StatefulWidget {
  const _DomainsSheet({required this.initial});

  final List<Json> initial;

  @override
  State<_DomainsSheet> createState() => _DomainsSheetState();
}

class _DomainsSheetState extends State<_DomainsSheet> {
  late List<Json> _list = widget.initial;
  final _input = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    final report = await fetchCapabilities();
    if (mounted) setState(() => _list = report.feedDomains);
  }

  Future<void> _add() async {
    final domain = normalizeDomain(_input.text);
    if (domain == null) {
      LnToast.show(
        context,
        context.t('ix_invalidDomain'),
        kind: LnToastKind.notice,
      );
      return;
    }
    setState(() => _busy = true);
    try {
      await addFeedDomain(domain);
      _input.clear();
      await _reload();
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _remove(Json source) async {
    final name = ltr(asStr(source['identifier']));
    if (!await _confirmRemove(context, name) || !mounted) return;
    setState(() => _busy = true);
    try {
      final id = asStr(source['id']);
      await setSourceActive(id, active: false);
      if (!mounted) return;
      setState(
        () => _list = [
          for (final s in _list)
            if (s['id'] != id) s,
        ],
      );
      LnToast.show(
        context,
        context.t('ix_removedX', [name]),
        action: (
          context.t('sh_undo'),
          () async {
            try {
              await setSourceActive(id, active: true);
              await _reload();
            } catch (_) {
              // The removal stands; the list shows the server's state on the next read.
            }
          },
        ),
      );
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final ln = context.ln;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_list.isNotEmpty) ...[
            LnSection(
              padding: EdgeInsets.zero,
              children: [
                for (final s in _list)
                  WrapTile(
                    icon: FIcons.globe,
                    title: ltr(asStr(s['identifier'])),
                    trailing: _RemoveButton(
                      label: context.t('ix_removeX', [asStr(s['identifier'])]),
                      onTap: _busy ? null : () => _remove(s),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: LnSpace.md),
          ],
          _AddRow(
            controller: _input,
            label: context.t('ix_newDomain'),
            hint: 'example.com',
            busy: _busy,
            onAdd: _add,
          ),
          const SizedBox(height: LnSpace.md),
          Text(
            context.t('ix_domainsNote'),
            style: ln.text.footnote.copyWith(color: ln.colors.fgMuted),
          ),
        ],
      ),
    );
  }
}

class _RemoveButton extends StatelessWidget {
  const _RemoveButton({required this.label, required this.onTap});

  final String label;
  final VoidCallback? onTap;

  // Its own button node with the tap action (as PillButton): the label sits on the tappable.
  @override
  Widget build(BuildContext context) => LnTappable(
    onTap: onTap,
    enabled: onTap != null,
    semanticLabel: label,
    child: ExcludeSemantics(
      child: SizedBox.square(
        dimension: 48,
        child: Icon(FIcons.x, color: context.ln.colors.fgMuted),
      ),
    ),
  );
}

/// «خلاصات RSS»: the news feeds, remove (asks) and add an https link.
Future<void> showFeedsSheet(BuildContext context, List<Json> feeds) =>
    showLnSheet<void>(
      context,
      title: context.t('ix_rssFeeds'),
      builder: (_) => _FeedsSheet(initial: feeds),
    );

class _FeedsSheet extends StatefulWidget {
  const _FeedsSheet({required this.initial});

  final List<Json> initial;

  @override
  State<_FeedsSheet> createState() => _FeedsSheetState();
}

class _FeedsSheetState extends State<_FeedsSheet> {
  late List<Json> _list = widget.initial;
  final _input = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  Future<void> _add() async {
    if (!isFeedUrl(_input.text)) {
      LnToast.show(
        context,
        context.t('ix_invalidLink'),
        kind: LnToastKind.notice,
      );
      return;
    }
    setState(() => _busy = true);
    try {
      await addFeed(_input.text);
      _input.clear();
      final report = await fetchCapabilities();
      if (mounted) setState(() => _list = report.feeds);
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _remove(Json feed) async {
    final name = isolate(asStr(feed['name']));
    if (!await _confirmRemove(context, name) || !mounted) return;
    setState(() => _busy = true);
    try {
      final id = asStr(feed['id']);
      await removeIntegration(id);
      if (!mounted) return;
      setState(
        () => _list = [
          for (final f in _list)
            if (f['id'] != id) f,
        ],
      );
      LnToast.show(context, context.t('ix_removedX', [name]));
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          LnSection(
            padding: EdgeInsets.zero,
            children: [
              if (_list.isEmpty)
                WrapTile(title: context.t('ix_noFeedsDot'))
              else
                for (final f in _list)
                  WrapTile(
                    icon: FIcons.rss,
                    title: isolate(asStr(f['name'])),
                    subtitle: asString(f['domain']) == null
                        ? null
                        : ltr(asStr(f['domain'])),
                    trailing: _RemoveButton(
                      label: context.t('ix_removeX', [asStr(f['name'])]),
                      onTap: _busy ? null : () => _remove(f),
                    ),
                  ),
            ],
          ),
          const SizedBox(height: LnSpace.md),
          _AddRow(
            controller: _input,
            label: context.t('ix_feedLink'),
            hint: 'https://…/feed.xml',
            busy: _busy,
            onAdd: _add,
          ),
        ],
      ),
    );
  }
}

/// «ربط Telegram»: linked → the masked token and «Unlink» (asks); not linked → the bot token
/// (write-only) and the agent that receives the owner's messages. Completes with the toast of
/// what was done, or null.
Future<String?> showTelegramSheet(
  BuildContext context, {
  required Json? telegram,
  required List<Agent> agents,
}) => showLnSheet<String>(
  context,
  title: context.t('ix_linkTelegram'),
  builder: (_) => _TelegramSheet(telegram: telegram, agents: agents),
);

class _TelegramSheet extends StatefulWidget {
  const _TelegramSheet({required this.telegram, required this.agents});

  final Json? telegram;
  final List<Agent> agents;

  @override
  State<_TelegramSheet> createState() => _TelegramSheetState();
}

class _TelegramSheetState extends State<_TelegramSheet> {
  final _token = TextEditingController();
  late String? _agentId =
      (widget.agents.where((a) => a.isPersonal).firstOrNull ??
              widget.agents.firstOrNull)
          ?.id;
  bool _busy = false;

  @override
  void dispose() {
    _token
      ..clear()
      ..dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final token = _token.text.trim();
    if (token.length < 8) {
      LnToast.show(context, context.t('ix_tooShort'), kind: LnToastKind.notice);
      return;
    }
    // The value leaves the field at once: it is sent once and never kept.
    _token.clear();
    setState(() => _busy = true);
    try {
      await linkTelegram(token, _agentId);
      if (mounted) Navigator.of(context).pop(context.t('ix_savedSecurely'));
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _unlink() async {
    final ok = await showLnConfirm(
      context,
      title: context.t('ix_unlinkTelegramQ'),
      confirmLabel: context.t('ix_unlink'),
      cancelLabel: context.t('sh_cancel'),
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _busy = true);
    try {
      await removeIntegration(asStr(widget.telegram!['id']));
      if (mounted) Navigator.of(context).pop(context.t('ix_telegramUnlinked'));
    } catch (e) {
      if (mounted) showErrorToast(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    ensureExtStrings(context);
    final ln = context.ln;
    final c = ln.colors;
    if (widget.telegram != null) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          MaskedSecret(caption: context.t('ix_savedNever')),
          const SizedBox(height: LnSpace.lg),
          BlockButton(
            label: context.t('ix_unlink'),
            variant: BlockButtonVariant.destructive,
            loading: _busy,
            onPressed: _busy ? null : _unlink,
          ),
        ],
      );
    }
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SecretField(
            controller: _token,
            label: context.t('ix_botToken'),
            hint: context.t('ix_pasteValue'),
            enabled: !_busy,
          ),
          const SizedBox(height: LnSpace.md),
          if (widget.agents.isNotEmpty) ...[
            LnSection(
              padding: EdgeInsets.zero,
              title: context.t('ix_messagesReach'),
              children: [
                for (final a in widget.agents)
                  ChoiceTile(
                    title: a.name,
                    icon: FIcons.bot,
                    selected: a.id == _agentId,
                    onSelect: () => setState(() => _agentId = a.id),
                  ),
              ],
            ),
            const SizedBox(height: LnSpace.md),
          ],
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(FIcons.lock, size: 16, color: c.fgMuted),
              const SizedBox(width: LnSpace.xs),
              Expanded(
                child: Text(
                  context.t('ix_valueEncrypted'),
                  style: ln.text.footnote.copyWith(color: c.fgMuted),
                ),
              ),
            ],
          ),
          const SizedBox(height: LnSpace.md),
          BlockButton(
            label: context.t('save'),
            loading: _busy,
            onPressed: _busy ? null : _save,
          ),
        ],
      ),
    );
  }
}
