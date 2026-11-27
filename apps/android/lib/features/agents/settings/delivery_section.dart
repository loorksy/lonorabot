// One agent's delivery rules (apps/web/src/shell/settings/NotifyPages.tsx `CommunicationPage`,
// `GET/PUT /agents/{id}/notifications`): in-app messages, agent calls and a daily limit (1–100,
// empty = none). Quiet hours are the owner's own, in Notifications and contact.
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../settings/settings_common.dart';
import '../profile/agent_data.dart';

class DeliverySection extends StatefulWidget {
  const DeliverySection({super.key, required this.agentId, this.dirty});

  final String agentId;

  /// Set to whether the draft differs from the saved rules (the page asks before leaving).
  final ValueNotifier<bool>? dirty;

  @override
  State<DeliverySection> createState() => _DeliverySectionState();
}

class _DeliverySectionState extends State<DeliverySection>
    with AutomaticKeepAliveClientMixin {
  /// Kept while scrolled out of the page's list, so a draft is not lost.
  @override
  bool get wantKeepAlive => true;

  DeliveryRules? _saved;
  DeliveryRules? _draft;
  Object? _error;
  bool _busy = false;
  final _limit = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _limit.dispose();
    super.dispose();
  }

  bool get _dirty {
    final draft = _draft;
    if (draft == null) return false;
    final limit = _typedLimit;
    return limit == -1 || _saved != draft.copyWith(dailyLimit: limit);
  }

  /// Applies [change] and reports whether the draft is now unsaved.
  void _update(VoidCallback change) {
    setState(change);
    widget.dirty?.value = _dirty;
  }

  Future<void> _load() async {
    try {
      final rules = await fetchDeliveryRules(widget.agentId);
      if (!mounted) return;
      _update(() {
        _saved = rules;
        _draft = rules;
        _error = null;
        _limit.text = rules.dailyLimit?.toString() ?? '';
      });
    } catch (error) {
      if (mounted) setState(() => _error = error);
    }
  }

  /// The typed limit: null for empty, -1 when it is not 1–100.
  int? get _typedLimit {
    final text = _limit.text.trim();
    if (text.isEmpty) return null;
    final value = int.tryParse(text);
    return value == null || value < 1 || value > 100 ? -1 : value;
  }

  Future<void> _save() async {
    final draft = _draft;
    if (draft == null || _busy || _typedLimit == -1) return;
    setState(() => _busy = true);
    try {
      final saved = await saveDeliveryRules(
        widget.agentId,
        draft.copyWith(dailyLimit: _typedLimit),
      );
      if (!mounted) return;
      _update(() => (_saved = saved, _draft = saved));
      LnToast.show(context, context.t('saved'), kind: LnToastKind.positive);
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final l10n = context.l10n;
    final draft = _draft;
    if (draft == null) {
      final error = _error;
      return LnSection(
        title: l10n.t('ag_notifications'),
        children: [
          WrapTile(
            icon: FIcons.bell,
            title: error == null
                ? l10n.t('sh_loading')
                : errorMessage(context, error) ?? l10n.t('request_failed'),
            trailing: error == null
                ? const LnSpinner(size: 18)
                : Icon(FIcons.rotateCw, color: context.ln.colors.fgMuted),
            onTap: error == null ? null : _load,
          ),
        ],
      );
    }
    final limit = _typedLimit;
    final dirty = _dirty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LnSection(
          title: l10n.t('ag_notifications'),
          footer: l10n.t('ag_quietHoursElsewhere'),
          children: [
            SwitchTile(
              icon: FIcons.messageSquare,
              title: l10n.t('ag_inApp'),
              value: draft.inApp,
              onChanged: _busy
                  ? null
                  : (v) => _update(() => _draft = draft.copyWith(inApp: v)),
            ),
            SwitchTile(
              icon: FIcons.phone,
              title: l10n.t('ag_agentCalls'),
              value: draft.calls,
              onChanged: _busy
                  ? null
                  : (v) => _update(() => _draft = draft.copyWith(calls: v)),
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter,
            LnSpace.sm,
            LnSpace.pageGutter,
            0,
          ),
          child: LnTextField(
            controller: _limit,
            label: l10n.t('ag_dailyLimit'),
            hint: l10n.t('ag_noLimit'),
            helper: l10n.t('ag_urgentAlways'),
            error: limit == -1 ? l10n.t('ag_limitInvalid') : null,
            enabled: !_busy,
            keyboardType: TextInputType.number,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(3),
            ],
            onChanged: (_) => _update(() {}),
          ),
        ),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.pageGutter,
            LnSpace.sm,
            LnSpace.pageGutter,
            0,
          ),
          child: BlockButton(
            label: l10n.t('save'),
            variant: BlockButtonVariant.secondary,
            loading: _busy,
            onPressed: dirty && limit != -1 ? _save : null,
          ),
        ),
      ],
    );
  }
}
