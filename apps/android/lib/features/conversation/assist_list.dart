// The composer's @ and «/» lists (apps/web/src/conversation/Composer.tsx `assist`, the rows of
// apps/mobile/components/thread-composer.tsx): a panel above the composer pill, not a popover,
// so the field keeps its focus and the keyboard stays open. Rows are 48 dp buttons.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../avatar/avatar.dart';
import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';
import '../chats/chat_text.dart' show agentRole, highlightRange;
import 'composer_assist.dart';
import 'conversation_strings.dart';

const Map<String, IconData> _commandIcons = {
  'task': LnIcons.listTodo,
  'search': FIcons.globe,
  'summary': FIcons.newspaper,
  'chart': FIcons.chartCandlestick,
  'call': FIcons.phone,
  'clear': FIcons.trash2,
  'skill': FIcons.zap,
};

/// The panel both lists share: the composer's surface, at most min(340 dp, 40 % of the room
/// above the keyboard), scrolling inside.
class _AssistPanel extends StatelessWidget {
  const _AssistPanel({required this.label, required this.children});

  final String label;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final room =
        MediaQuery.sizeOf(context).height -
        MediaQuery.viewInsetsOf(context).bottom;
    return Semantics(
      container: true,
      explicitChildNodes: true,
      label: label,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: (room * 0.4).clamp(0, 340)),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: c.surface,
            borderRadius: const BorderRadius.all(
              Radius.circular(LnRadius.card),
            ),
            border: Border.all(color: c.border),
            boxShadow: ln.chromeShadow,
          ),
          child: ClipRRect(
            borderRadius: const BorderRadius.all(
              Radius.circular(LnRadius.card - 1),
            ),
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: children,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(14, 8, 14, 2),
      child: ExcludeSemantics(
        child: Text(
          text,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: ln.text.footnote.copyWith(color: ln.colors.fgMuted),
        ),
      ),
    );
  }
}

/// One row: a leading icon or avatar, the title and an optional line under it, an optional
/// trailing label; a 48 dp button read as [semanticLabel].
class _AssistRow extends StatelessWidget {
  const _AssistRow({
    required this.leading,
    required this.title,
    required this.semanticLabel,
    required this.onTap,
    this.sub,
    this.trailing,
  });

  final Widget leading;
  final Widget title;
  final String? sub;
  final Widget? trailing;
  final String semanticLabel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final line = sub;
    return LnTappable(
      onTap: onTap,
      pressScale: 1,
      semanticLabel: semanticLabel,
      excludeChildSemantics: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: LnSize.minTouch),
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(12, 6, 14, 6),
          child: Row(
            children: [
              SizedBox(width: 28, child: Center(child: leading)),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    title,
                    if (line != null && line.isNotEmpty)
                      Text(
                        line,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textDirection: textDirectionFor(
                          line,
                          Directionality.of(context),
                        ),
                        style: ln.text.footnote.copyWith(color: c.fgMuted),
                      ),
                  ],
                ),
              ),
              if (trailing != null) ...[const SizedBox(width: 8), trailing!],
            ],
          ),
        ),
      ),
    );
  }
}

/// The «/» list: the chat's commands («الأوامر»), then «مهارات {agent}»; the part of a name the
/// query matched is bold, the hint follows in italics, the English name trails when it differs.
/// [rows] empty shows «لا يوجد أمر بهذا الاسم».
class CommandList extends StatelessWidget {
  const CommandList({
    super.key,
    required this.rows,
    required this.query,
    required this.agentName,
    required this.onPick,
  });

  final List<CommandOption> rows;
  final String query;
  final String agentName;
  final ValueChanged<CommandOption> onPick;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    registerConversationStrings(l10n);
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final slash = rtl ? '\u200f/' : '/';
    final children = <Widget>[];
    if (rows.isEmpty) {
      children.add(
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
          child: Text(
            l10n.t('conv_noCommand'),
            style: ln.text.footnote.copyWith(color: c.fgMuted),
          ),
        ),
      );
    }
    for (final (i, row) in rows.indexed) {
      if (i == 0 || row.skill != rows[i - 1].skill) {
        children.add(
          _Section(
            row.skill
                ? l10n.t('conv_skillsOf', [isolate(agentName)])
                : l10n.t('cmdList'),
          ),
        );
      }
      final mark = highlightRange(row.name, query);
      final strong = ln.text.title.copyWith(color: c.fg);
      final name = mark == null
          ? [TextSpan(text: row.name, style: strong)]
          : [
              TextSpan(text: row.name.substring(0, mark.$1), style: strong),
              TextSpan(
                text: row.name.substring(mark.$1, mark.$2),
                style: strong.copyWith(fontWeight: FontWeight.w700),
              ),
              TextSpan(text: row.name.substring(mark.$2), style: strong),
            ];
      final alias = row.alias;
      children.add(
        _AssistRow(
          leading: Icon(
            _commandIcons[row.command] ?? FIcons.zap,
            size: 20,
            color: row.command == 'clear' ? c.error : c.fgMuted,
          ),
          title: Text.rich(
            TextSpan(
              children: [
                TextSpan(text: slash, style: strong),
                ...name,
                if (row.hint != null)
                  TextSpan(
                    text: ' ${row.hint}',
                    style: ln.text.footnote.copyWith(
                      color: c.fgSubtle,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
              ],
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textDirection: textDirectionFor(
              row.name,
              Directionality.of(context),
            ),
          ),
          sub: row.sub,
          trailing: alias != null && alias != row.name
              ? Text(
                  ltr('/$alias'),
                  style: ln.text.footnote.copyWith(color: c.fgSubtle),
                )
              : null,
          semanticLabel: [
            '/${row.name}',
            if ((row.sub ?? '').isNotEmpty) row.sub!,
          ].join(listSeparator(l10n.lang)),
          onTap: () => onPick(row),
        ),
      );
    }
    return _AssistPanel(label: l10n.t('cmdList'), children: children);
  }
}

/// The @ list: the group's members («أعضاء المجموعة», the lead tagged «القائد») or the agents a
/// direct chat can bring in («إشراك وكيل في المحادثة»), then «@الكل» where it applies (a null
/// option); in a group its line says how many agents it alerts.
class MentionList extends StatelessWidget {
  const MentionList({
    super.key,
    required this.options,
    required this.group,
    required this.onPick,
    this.leadId,
    this.alerted = 0,
  });

  final List<Agent?> options;
  final bool group;
  final String? leadId;

  /// The group's non-paused members (the @all row's count).
  final int alerted;
  final ValueChanged<Agent?> onPick;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    registerConversationStrings(l10n);
    final ui = Directionality.of(context);
    final title = ln.text.title.copyWith(color: c.fg);
    final allWord = '@${l10n.t('conv_all')}';
    return _AssistPanel(
      label: l10n.t('conv_mentionList'),
      children: [
        _Section(l10n.t(group ? 'conv_groupMembers' : 'conv_bringAgent')),
        for (final agent in options)
          if (agent == null)
            _AssistRow(
              leading: Icon(FIcons.users, size: 20, color: c.fgMuted),
              title: Text(allWord, style: title),
              sub: group ? alertsText(l10n.lang, alerted) : null,
              semanticLabel: [
                allWord,
                if (group) alertsText(l10n.lang, alerted),
              ].join(listSeparator(l10n.lang)),
              onTap: () => onPick(null),
            )
          else
            _AssistRow(
              leading: LonoraAvatar(
                agentId: agent.id,
                face: agent.avatar,
                color: agent.color,
                tradesOnItsOwn: agent.tradesOnItsOwn,
                size: 24,
                animate: false,
              ),
              title: Text(
                '@${agent.name}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textDirection: textDirectionFor(agent.name, ui),
                style: title,
              ),
              sub: agentRole(l10n, agent),
              trailing: agent.id == leadId
                  ? Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 2,
                      ),
                      decoration: ShapeDecoration(
                        color: c.fill3,
                        shape: const StadiumBorder(),
                      ),
                      child: Text(
                        l10n.t('conv_lead'),
                        style: ln.text.smallStrong.copyWith(color: c.fgMuted),
                      ),
                    )
                  : null,
              semanticLabel: [
                '@${agent.name}',
                if (agentRole(l10n, agent).isNotEmpty) agentRole(l10n, agent),
                if (agent.id == leadId) l10n.t('conv_lead'),
              ].join(listSeparator(l10n.lang)),
              onTap: () => onPick(agent),
            ),
      ],
    );
  }
}
