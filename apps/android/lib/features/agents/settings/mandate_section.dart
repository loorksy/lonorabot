// The agent's trading Mandate (Full / Ask), exactly as the Expo settings row and the Web chip
// menu change it (apps/mobile/components/agent-permissions.tsx, apps/web PermissionMenu.tsx):
// the settings row only opens the Mandate sheet, which shows the current mode and its line;
// changing it needs the agent's live Mandate card (`GET /owner-actions/mandate`, read when the
// sheet opens, which never raises one); without a card the owner may ask for one («show the
// card», `POST /owner-actions/mandate`); the mode is applied only by the owner's tap on the
// button naming that mode inside the sheet (`POST /owner-actions/{card}/decision {decision:
// confirm, trading_mode}`). A refused decision re-reads the live card (lonora-api-contract
// §19.4). Nothing here changes a mode by itself. An agent with no connected account shows
// nothing (Q9). Lonora has no paper/live switch: the only per-agent trading control is this
// mode (lonora-api-contract §11.3).
import 'package:async_redux/async_redux.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../../core/json.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../../state/actions/shell_actions.dart';
import '../../settings/settings_common.dart';
import '../profile/agent_data.dart';
import '../profile/agent_page.dart';

String? _mode(Agent agent) => switch (agent.tradingMode) {
  'full' => 'full',
  'ask' => 'ask',
  _ => null,
};

class MandateSection extends StatelessWidget {
  const MandateSection({super.key, required this.agent, this.unresolved});

  final Agent agent;

  /// Operations whose broker result is unconfirmed (`trading_readiness.unresolved_count`).
  final int? unresolved;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final words = ownerActionText(l10n.lang);
    final mode = _mode(agent);
    // The row's own line is the mode's first clause; its whole line is in the sheet.
    return LnSection(
      title: l10n.t('ag_trading'),
      children: [
        WrapTile(
          icon: mode == 'full' ? FIcons.triangleAlert : FIcons.shieldCheck,
          title: mandateLine(mode, l10n.lang) ?? l10n.t('ag_modeUnknown'),
          subtitle: tradingSubLine(unresolved, mode, l10n.lang),
          trailing: const TileChevron(),
          // Opens the Mandate sheet; only a button inside it applies a mode.
          onTap: () => showLnSheet<void>(
            context,
            title: '${words.mandateTitle} · ${isolate(agent.name)}',
            builder: (_) => MandateSheet(agent: agent),
          ),
        ),
      ],
    );
  }
}

/// The Mandate sheet: «الآن: …», the mode's line, the other mode's button (or «show the card»)
/// and Close (apps/mobile/components/agent-permissions.tsx `sheet`).
class MandateSheet extends StatefulWidget {
  const MandateSheet({super.key, required this.agent});

  final Agent agent;

  @override
  State<MandateSheet> createState() => _MandateSheetState();
}

class _MandateSheetState extends State<MandateSheet> {
  Json? _card;
  bool _read = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _readCard();
  }

  Future<void> _readCard() async {
    try {
      final card = await fetchMandate(widget.agent.id);
      if (mounted) setState(() => (_card = card, _read = true));
    } catch (_) {
      if (mounted) setState(() => (_card = null, _read = true));
    }
  }

  Future<void> _showCard() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final card = await raiseMandate(widget.agent.id);
      if (mounted) setState(() => _card = card);
    } catch (error) {
      if (mounted) showErrorToast(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _apply(String mode) async {
    final card = _card;
    if (card == null || _busy) return;
    setState(() => _busy = true);
    try {
      final updated = await decideMandate(asStr(card['id']), mode);
      if (!mounted) return;
      final result = asJson(updated['result']);
      final applied = appliedTradingMode(result);
      final agent = widget.agent;
      context.dispatch(
        UpsertAgentAction(
          Agent.fromJson({...agent.raw, 'trading_mode': applied}),
        ),
      );
      LnToast.show(
        context,
        modeChangeLine(
          agent.name,
          applied,
          asInt(result['withdrawn']) ?? 0,
          context.l10n.lang,
        ),
        kind: LnToastKind.positive,
      );
      Navigator.of(context).pop();
    } catch (error) {
      if (!mounted) return;
      showErrorToast(context, error);
      // Already decided, expired or superseded: the next tap acts on the live card.
      setState(() => (_card = null, _read = false));
      await _readCard();
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final ln = context.ln;
    final words = ownerActionText(l10n.lang);
    final mode = _mode(widget.agent);
    final other = otherTradingMode(mode);
    final card = _card;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (mode != null) ...[
          Text(
            '${words.mandateNow}: ${mode == 'full' ? words.modeFull : words.modeAsk}',
            style: ln.text.body.copyWith(color: ln.colors.fg),
          ),
          const SizedBox(height: LnSpace.xs),
          Text(
            mode == 'full' ? words.modeFullLine : words.modeAskLine,
            style: ln.text.footnote.copyWith(color: ln.colors.fgMuted),
          ),
        ],
        const SizedBox(height: LnSpace.lg),
        if (other != null && card != null)
          BlockButton(
            label: other == 'full' ? words.modeFull : words.modeAsk,
            icon: other == 'full' ? FIcons.triangleAlert : FIcons.shieldCheck,
            loading: _busy,
            onPressed: () => _apply(other),
          )
        else if (other != null && _read && card == null)
          BlockButton(
            label: words.mandateRequest,
            icon: FIcons.fileCheck,
            variant: BlockButtonVariant.secondary,
            loading: _busy,
            onPressed: _showCard,
          )
        else if (other != null)
          const Center(child: LnSpinner()),
        const SizedBox(height: LnSpace.xs),
        BlockButton(
          label: l10n.t('close'),
          variant: BlockButtonVariant.secondary,
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
        ),
      ],
    );
  }
}
