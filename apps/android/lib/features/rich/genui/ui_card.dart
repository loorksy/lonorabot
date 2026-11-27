// A lonora-ui v2 card on Android, natively: the twin of apps/mobile/components/genui/card.tsx
// and nodes.tsx, drawn with the Lonora kit (bordered card surface, 16 dp padding, stadium block
// buttons, the 12-style type scale). The server compiled and checked the card; this renders it
// with the ported evaluator, keeps its values, and sends only `MessageCreate.ui_submit`. While
// the card builds, and until its message is committed, every control is disabled; while it is
// locked only go, open and copy stay enabled. A card never approves, settles or switches a
// mode: a trusted Slot draws the live fixed card with its own owner-session buttons.
import 'dart:async';

import 'package:async_redux/async_redux.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../app/routes.dart';
import '../../../core/api/api_error.dart';
import '../../../core/json.dart';
import '../../../core/models/models.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../../state/actions/base.dart';
import '../../../state/app_state.dart';
import '../../cards/fixed_cards.dart';
import '../rich_actions.dart';
import '../rich_slider.dart';
import 'card_icon.dart';
import 'expr.dart';
import 'spec.dart';

const Duration _staleAfter = Duration(seconds: 120);

/// The server's `go` routes on Android's own screens.
String? _route(String name) => switch (name) {
  'market' => Routes.charts(),
  'tasks' => Routes.tasks,
  'usage' => Routes.usage,
  'files' => Routes.artifacts(),
  'agents' => Routes.agents,
  _ => null,
};

/// Disclosures the owner opened, so a list redraw keeps them open.
final Set<String> _openedMore = {};

class UiCardView extends StatefulWidget {
  const UiCardView({
    super.key,
    required this.part,
    required this.index,
    required this.threadId,
    this.messageId,
  });

  final UiPart part;

  /// The part's stored index (a submission names its part by it).
  final int index;
  final String threadId;

  /// The committed message id; null while the card is a live preview.
  final String? messageId;

  @override
  State<UiCardView> createState() => _UiCardViewState();
}

class _UiCardViewState extends State<UiCardView> {
  Json get _doc => widget.part.document;
  late Map<String, Object?> _values;
  String? _invalid;
  final Set<String> _unreadable = {};
  String? _notice;
  bool _sending = false;
  String? _sentHere;
  bool _whyOpen = false;
  Timer? _flash;
  final Map<String, FocusNode> _focus = {};

  @override
  void initState() {
    super.initState();
    _values = {...asJson(_doc['state'])};
  }

  bool _seeded = false;

  void _seed(Message? message) {
    if (_seeded || message == null) return;
    _seeded = true;
    final saved = asJson(
      asJson(asJson(message.uiState?['parts'])['${widget.index}'])['values'],
    );
    if (saved.isNotEmpty) _values = {...asJson(_doc['state']), ...saved};
  }

  @override
  void dispose() {
    _flash?.cancel();
    for (final f in _focus.values) {
      f.dispose();
    }
    super.dispose();
  }

  FocusNode _focusFor(String key) => _focus[key] ??= FocusNode();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // Only what this card draws from the store: its message, its lock, whether sending is
    // blocked, and whether its own submission arrived (not the whole thread).
    final messageId = widget.messageId;
    final sent = _sentHere;
    final view = context.select((AppState s) {
      final t = s.thread(widget.threadId);
      final message = messageId == null
          ? null
          : t.messages.where((m) => m.id == messageId).firstOrNull;
      final agentId = message?.agentId ?? asString(_doc['agent_id']);
      final agent = agentId == null ? null : s.shell.agents[agentId];
      if (message == null) {
        return (
          message: null,
          agent: agent,
          lock: null,
          blocked: null,
          arrived: false,
        );
      }
      return (
        message: message,
        agent: agent,
        lock: cardLock(message, widget.index, t.messages),
        blocked: sendBlocked(
          agentId,
          widget.threadId,
          t.messages,
          t.runs.values,
          paused: agent?.paused ?? false,
        ),
        arrived: sent != null && t.messages.any((m) => m.clientNonce == sent),
      );
    });
    final message = view.message;
    final agent = view.agent;
    _seed(message);
    final facts = {
      for (final MapEntry(:key, :value) in asJson(_doc['facts']).entries)
        key: asJson(value)['value'],
    };
    final env = environment(
      asJson(_doc['state']),
      asJson(_doc['calc']),
      facts,
      values: _values,
      context: FormatContext(
        currency: asString(_doc['currency']),
        language: l10n.lang,
      ),
    );
    final lock = view.lock;
    final awaiting = sent != null && !view.arrived;
    final locked = lock != null || awaiting;
    final blocked = view.blocked;
    final oldest = _oldestFact();
    final building = widget.part.building;
    final committed = message != null;
    final ctx = _CardCtx(
      env: env,
      values: _values,
      locked: locked,
      frozen: building || !committed || _sending,
      invalid: _invalid,
      sendOff: blocked != null || _unreadable.isNotEmpty || !committed,
      cardKey: '${widget.messageId ?? 'preview'}:${widget.index}',
      threadId: widget.threadId,
      stale: (text) => _stale(text, oldest, l10n),
      pick: (key, value, also) {
        if (locked) return;
        HapticFeedback.selectionClick();
        setState(() {
          _values = {..._values, key: value, ...?also};
          if (also != null && also.containsKey(_invalid)) _invalid = null;
        });
      },
      type: (key, value) => setState(() {
        _values = {..._values, key: value};
        if (_invalid == key) _invalid = null;
      }),
      markUnreadable: (key, bad) {
        if (_unreadable.contains(key) == bad) return;
        setState(() => bad ? _unreadable.add(key) : _unreadable.remove(key));
      },
      focusFor: _focusFor,
      act: (block, path) => _act(block, path, env, message),
      submitPrimary: () {},
      redraw: () => setState(() {}),
    );
    ctx.submitPrimary = () {
      final found = _primary(asJsonList(_doc['blocks']), ctx, '');
      if (found != null && !_buttonOff(found.$1, ctx)) {
        _act(found.$1, found.$2, env, message);
      } else {
        _checkRequired(ctx, env);
      }
    };

    final ln = context.ln;
    final c = ln.colors;
    final cut = widget.part.cut;
    if (cut == 0) {
      // Stopped before any block was built: no card, its fallback text (review E2).
      return Text(
        asStr(_doc['fallback']),
        style: ln.text.body.copyWith(color: c.fg),
      );
    }
    final title = renderTemplate(asStr(_doc['title']), env);
    final sub = asString(_doc['sub']);
    final why = asString(_doc['why']);
    final blocks = asJsonList(_doc['blocks']);
    final showFoot = !building && (locked || why != null || cut != null);
    final icon = _doc['icon'];

    return Semantics(
      container: true,
      label: title.isEmpty ? l10n.t('uiCard') : title,
      child: LnCardSurface(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                LnSpace.cardPadding,
                LnSpace.cardPadding,
                LnSpace.cardPadding,
                0,
              ),
              child: Row(
                children: [
                  if (CardIcon.has(icon)) ...[
                    Container(
                      width: LnSize.iconTile,
                      height: LnSize.iconTile,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: c.surface,
                        borderRadius: const BorderRadius.all(
                          Radius.circular(LnRadius.iconTile),
                        ),
                        border: Border.all(color: c.border),
                      ),
                      child: CardIcon(icon, size: 20, color: c.fg),
                    ),
                    const SizedBox(width: LnSpace.sm),
                  ],
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Semantics(
                          header: true,
                          child: Text(
                            title,
                            style: ln.text.title.copyWith(color: c.fg),
                          ),
                        ),
                        if (sub != null)
                          Text(
                            renderTemplate(sub, env),
                            style: ln.text.footnote.copyWith(color: c.fgMuted),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(LnSpace.cardPadding),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (var i = 0; i < blocks.length; i++)
                    if (cut == null || i < cut) ...[
                      if (i > 0 && _visible(blocks[i], env))
                        const SizedBox(height: 14),
                      // A sent card dims its own blocks; a trusted slot never dims.
                      Opacity(
                        opacity: locked && blocks[i]['type'] != 'Slot'
                            ? 0.82
                            : 1,
                        child: _UiNode(block: blocks[i], path: '$i', ctx: ctx),
                      ),
                    ],
                  if (building) ...[
                    if (blocks.isNotEmpty) const SizedBox(height: 14),
                    const _Skeleton(),
                  ],
                ],
              ),
            ),
            if (_notice != null)
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(
                  LnSpace.cardPadding,
                  0,
                  LnSpace.cardPadding,
                  LnSpace.sm,
                ),
                child: Semantics(
                  liveRegion: true,
                  child: Text(
                    _notice!,
                    style: ln.text.footnote.copyWith(color: c.warning),
                  ),
                ),
              ),
            if (showFoot)
              _Footer(
                locked: locked,
                cut: cut != null,
                why: why,
                whyOpen: _whyOpen,
                agentName: agent?.name,
                oldest: oldest,
                onWhy: () => setState(() => _whyOpen = !_whyOpen),
                onUnlock: message == null ? null : () => _unlock(message),
              ),
          ],
        ),
      ),
    );
  }

  DateTime? _oldestFact() {
    DateTime? oldest;
    for (final fact in asJson(_doc['facts']).values) {
      final at = DateTime.tryParse(asStr(asJson(fact)['observed_at']));
      if (at != null && (oldest == null || at.isBefore(oldest))) oldest = at;
    }
    return oldest;
  }

  String _stale(String text, DateTime? oldest, L10n l10n) {
    // «الآن» over a fact older than 120 s reads «آخر تحديث HH:MM» (docs/genui.md §8).
    if (oldest == null || DateTime.now().difference(oldest) <= _staleAfter) {
      return text;
    }
    return text.replaceFirst(
      RegExp(r'^(الآن|now)(?=[\s:،,.]|$)', caseSensitive: false),
      '${l10n.t('uiLastUpdated')} ${clockTime(oldest, lang: l10n.lang)}',
    );
  }

  Json? _requiredMissing(List<Json> blocks, _CardCtx ctx) {
    for (final block in blocks) {
      if (!_visible(block, ctx.env)) continue;
      final bind = asString(block['bind']);
      final value = bind == null ? null : _values[bind];
      if (block['required'] == true && (value == null || value == '')) {
        return block;
      }
      final missing = _requiredMissing(asJsonList(block['children']), ctx);
      if (missing != null) return missing;
    }
    return null;
  }

  bool _checkRequired(_CardCtx ctx, Env env) {
    final missing = _requiredMissing(asJsonList(_doc['blocks']), ctx);
    if (missing == null) return true;
    final key = asStr(missing['bind']);
    setState(() {
      _invalid = key;
      _notice = context.t('uiCompleteFirst', [
        renderTemplate(asStr(missing['label']), env),
      ]);
    });
    _focus[key]?.requestFocus();
    return false;
  }

  (Json, String)? _primary(List<Json> blocks, _CardCtx ctx, String prefix) {
    for (var i = 0; i < blocks.length; i++) {
      final block = blocks[i];
      final path = prefix.isEmpty ? '$i' : '$prefix.$i';
      if (!_visible(block, ctx.env)) continue;
      if (block['type'] == 'Button' && block['style'] == 'primary') {
        return (block, path);
      }
      if (block['type'] == 'More' &&
          !_openedMore.contains('${ctx.cardKey}:$path')) {
        continue;
      }
      final inner = _primary(asJsonList(block['children']), ctx, path);
      if (inner != null) return inner;
    }
    return null;
  }

  Future<void> _act(Json block, String path, Env env, Message? message) async {
    final action = asJson(block['action']);
    final kind = asString(action['do']) ?? 'send';
    switch (kind) {
      case 'send':
        await _send(block, path, env, message);
      case 'go':
        final location = _route(asStr(action['route']));
        if (location != null) await GoRouter.maybeOf(context)?.push(location);
      case 'open':
        // A literal https URL the server matched to the owner's message or a tool result.
        final url = asStr(action['url']);
        final uri = Uri.tryParse(url);
        if (url.startsWith('https://') && uri != null) {
          await launchUrl(uri, mode: LaunchMode.externalApplication);
        }
      case 'copy':
        await Clipboard.setData(
          ClipboardData(text: renderTemplate(asStr(action['text']), env)),
        );
        unawaited(HapticFeedback.selectionClick());
        if (mounted) _flashNotice(context.t('uiCopied'));
      case 'set':
        final value = evaluate(
          action['value'],
          env.withContext(env.context.withRandom()),
        );
        setState(() => _values = {..._values, asStr(action['key']): value});
      case 'toggle':
        final key = asStr(action['key']);
        setState(() => _values = {..._values, key: !truthy(_values[key])});
      case 'reset':
        setState(() => _values = {...asJson(_doc['state'])});
    }
  }

  void _flashNotice(String text) {
    setState(() => _notice = text);
    _flash?.cancel();
    _flash = Timer(const Duration(milliseconds: 1600), () {
      if (mounted && _notice == text) setState(() => _notice = null);
    });
  }

  Future<void> _send(Json block, String path, Env env, Message? message) async {
    if (message == null || _sending || _unreadable.isNotEmpty) return;
    final ctx = _CardCtx.check(env);
    if (!_checkRequired(ctx, env)) return;
    final action = SubmitCardAction(
      threadId: widget.threadId,
      messageId: message.id,
      part: widget.index,
      path: path,
      values: Map.of(_values),
    );
    setState(() {
      _sending = true;
      _notice = null;
    });
    unawaited(HapticFeedback.selectionClick());
    try {
      await context.dispatchAndWait(action);
      // Locked at once; the submission's own message then carries the lock.
      if (asJson(block['action'])['lock'] != false && mounted) {
        setState(() => _sentHere = action.nonce);
      }
    } on ApiError catch (e) {
      if (mounted) setState(() => _notice = context.l10n.errorText(e.code));
    } on SessionRequestCancelled {
      // Signed out: nothing to show.
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _unlock(Message message) async {
    try {
      await context.dispatchAndWait(
        UnlockCardAction(
          threadId: widget.threadId,
          message: message,
          part: widget.index,
        ),
      );
      if (!mounted) return;
      setState(() {
        _sentHere = null;
        _notice = context.t('uiEditThenSend');
      });
    } on ApiError catch (e) {
      if (mounted) setState(() => _notice = context.l10n.errorText(e.code));
    } on SessionRequestCancelled {
      // Signed out.
    }
  }
}

bool _visible(Json block, Env env) =>
    !block.containsKey('when') || truthy(evaluate(block['when'], env, false));

/// Everything a node needs from its card.
class _CardCtx {
  _CardCtx({
    required this.env,
    required this.values,
    required this.locked,
    required this.frozen,
    required this.invalid,
    required this.sendOff,
    required this.cardKey,
    required this.threadId,
    required this.stale,
    required this.pick,
    required this.type,
    required this.markUnreadable,
    required this.focusFor,
    required this.act,
    required this.submitPrimary,
    required this.redraw,
  });

  /// A context only for the required-field walk (visibility needs the environment alone).
  factory _CardCtx.check(Env env) => _CardCtx(
    env: env,
    values: env.values,
    locked: false,
    frozen: false,
    invalid: null,
    sendOff: false,
    cardKey: '',
    threadId: '',
    stale: (t) => t,
    pick: (_, _, _) {},
    type: (_, _) {},
    markUnreadable: (_, _) {},
    focusFor: (_) => FocusNode(),
    act: (_, _) {},
    submitPrimary: () {},
    redraw: () {},
  );

  final Env env;
  final Map<String, Object?> values;
  final bool locked;
  final bool frozen;
  final String? invalid;
  final bool sendOff;
  final String cardKey;
  final String threadId;
  final String Function(String) stale;
  final void Function(String key, Object? value, Map<String, Object?>? also)
  pick;
  final void Function(String key, Object? value) type;
  final void Function(String key, bool bad) markUnreadable;
  final FocusNode Function(String key) focusFor;
  final void Function(Json block, String path) act;
  VoidCallback submitPrimary;
  final VoidCallback redraw;

  String text(Object? value) =>
      stale(renderTemplate(value is String ? value : jsString(value), env));

  bool get controlsOff => frozen || locked;
}

String jsString(Object? value) => value == null ? '' : show(value);

/// Whether a Button is off now: the rule a tap and Enter in a Number field both follow.
bool _buttonOff(Json block, _CardCtx ctx) {
  final action = block['action'];
  final kind = action is Map ? action['do'] : null;
  final safe = const ['go', 'open', 'copy'].contains(kind);
  final sends = action == null || kind == 'send';
  return ctx.frozen ||
      (!safe && (ctx.locked || (sends && ctx.sendOff))) ||
      // A `disabled` that fails to evaluate disables, as the server refuses it.
      (block.containsKey('disabled') &&
          truthy(evaluate(block['disabled'], ctx.env, true)));
}

class _UiNode extends StatelessWidget {
  const _UiNode({required this.block, required this.path, required this.ctx});

  final Json block;
  final String path;
  final _CardCtx ctx;

  @override
  Widget build(BuildContext context) {
    if (!_visible(block, ctx.env)) return const SizedBox.shrink();
    final ln = context.ln;
    final c = ln.colors;
    switch (asStr(block['type'])) {
      case 'Segmented':
        return _Segmented(block: block, ctx: ctx);
      case 'Select':
        return _Select(block: block, ctx: ctx);
      case 'Number':
        return _NumberField(block: block, ctx: ctx);
      case 'Slider':
        return _Slider(block: block, ctx: ctx);
      case 'Text':
        final tone = block['tone'];
        final color = tone == 'muted'
            ? c.fgMuted
            : tone == 'accent'
            ? c.brand
            : c.fg;
        final style =
            (block['size'] == 'sm' ? ln.text.footnote : ln.text.caption)
                .copyWith(color: color);
        return Semantics(
          liveRegion: true,
          child: _inline(cardInline(ctx.text(block['text'])), style),
        );
      case 'Title':
        return Semantics(
          header: true,
          child: Text(
            ctx.text(block['text']),
            style: ln.text.title.copyWith(
              color: c.fg,
              fontWeight: FontWeight.w600,
            ),
          ),
        );
      case 'Markdown':
        return _CardMarkdown(text: ctx.text(block['text']));
      case 'Note':
        return _Note(block: block, ctx: ctx);
      case 'Badge':
        final good = block['tone'] == 'accent' || block['tone'] == 'good';
        return Align(
          alignment: AlignmentDirectional.centerStart,
          child: StatusChip(
            label: ctx.text(block['text']),
            kind: good
                ? StatusChipKind.brand
                : block['tone'] == 'warn'
                ? StatusChipKind.waiting
                : block['tone'] == 'bad'
                ? StatusChipKind.error
                : StatusChipKind.neutral,
          ),
        );
      case 'KeyValue':
        final rows = (block['rows'] as List?) ?? const [];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var i = 0; i < rows.length; i++)
              Container(
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  border: i < rows.length - 1
                      ? Border(bottom: BorderSide(color: c.border))
                      : null,
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        ctx.text(_cell(rows[i], 0)),
                        style: ln.text.caption.copyWith(color: c.fgMuted),
                      ),
                    ),
                    const SizedBox(width: LnSpace.md),
                    ConstrainedBox(
                      constraints: BoxConstraints(
                        maxWidth: MediaQuery.sizeOf(context).width * 0.45,
                      ),
                      child: Text(
                        ctx.text(_cell(rows[i], 1)),
                        textAlign: TextAlign.end,
                        style: ln.text.captionStrong.copyWith(color: c.fg),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        );
      case 'Stat':
        return _Stat(block: block, ctx: ctx);
      case 'Button':
        return _Button(block: block, path: path, ctx: ctx);
      case 'Divider':
        return Container(height: 1, color: c.border);
      case 'Row':
        final children = asJsonList(block['children']);
        final visible = [
          for (var i = 0; i < children.length; i++)
            if (_visible(children[i], ctx.env)) i,
        ];
        if (visible.isNotEmpty &&
            visible.every((i) => children[i]['type'] == 'Button')) {
          // Buttons share a row equally (web `.ux-row > .btn` grows).
          return Row(
            children: [
              for (var k = 0; k < visible.length; k++) ...[
                if (k > 0) const SizedBox(width: LnSpace.xs),
                Expanded(
                  child: _UiNode(
                    block: children[visible[k]],
                    path: '$path.${visible[k]}',
                    ctx: ctx,
                  ),
                ),
              ],
            ],
          );
        }
        return Wrap(
          spacing: LnSpace.xs,
          runSpacing: LnSpace.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            for (final i in visible)
              _UiNode(block: children[i], path: '$path.$i', ctx: ctx),
          ],
        );
      case 'Col':
        return _Children(block: block, path: path, ctx: ctx, gap: 12);
      case 'Grid':
        return _Grid(block: block, path: path, ctx: ctx);
      case 'Card':
        return Container(
          padding: const EdgeInsets.all(LnSpace.sm),
          decoration: BoxDecoration(
            color: c.fill1,
            borderRadius: const BorderRadius.all(
              Radius.circular(LnRadius.field),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (block.containsKey('title')) ...[
                Row(
                  children: [
                    if (CardIcon.has(block['icon'])) ...[
                      CardIcon(block['icon'], size: 16, color: c.fg),
                      const SizedBox(width: 6),
                    ],
                    Expanded(
                      child: Text(
                        ctx.text(block['title']),
                        style: ln.text.captionStrong.copyWith(color: c.fg),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
              ],
              _Children(block: block, path: path, ctx: ctx, gap: 10),
            ],
          ),
        );
      case 'More':
        return _More(block: block, path: path, ctx: ctx);
      case 'Slot':
        return _Slot(block: block, ctx: ctx);
      case 'Delivery':
        return _Delivery(block: block);
    }
    return const SizedBox.shrink();
  }

  static Object? _cell(Object? row, int i) =>
      row is List && i < row.length ? row[i] : '';
}

Widget _inline(List<CardInline> pieces, TextStyle style) => Text.rich(
  TextSpan(
    style: style,
    children: [
      for (final p in pieces)
        TextSpan(
          text: p.text,
          style: p.bold ? const TextStyle(fontWeight: FontWeight.w700) : null,
        ),
    ],
  ),
);

class _Children extends StatelessWidget {
  const _Children({
    required this.block,
    required this.path,
    required this.ctx,
    required this.gap,
  });
  final Json block;
  final String path;
  final _CardCtx ctx;
  final double gap;

  @override
  Widget build(BuildContext context) {
    final children = asJsonList(block['children']);
    final shown = [
      for (var i = 0; i < children.length; i++)
        if (_visible(children[i], ctx.env)) i,
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var k = 0; k < shown.length; k++) ...[
          if (k > 0) SizedBox(height: gap),
          _UiNode(
            block: children[shown[k]],
            path: '$path.${shown[k]}',
            ctx: ctx,
          ),
        ],
      ],
    );
  }
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel({required this.label, this.aside});
  final String label;
  final Widget? aside;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Text(
              label,
              style: ln.text.footnoteStrong.copyWith(color: ln.colors.fgMuted),
            ),
          ),
          ?aside,
        ],
      ),
    );
  }
}

class _Option {
  const _Option(this.value, this.label, this.also);
  final Object? value;
  final String label;
  final Map<String, Object?>? also;
}

List<_Option> _options(Object? options, _CardCtx ctx) => [
  for (final option in (options is List ? options : const []))
    option is Map
        ? _Option(
            option['value'],
            renderTemplate(
              jsString(option['label'] ?? option['value']),
              ctx.env,
            ),
            option['also'] is Map ? asJson(option['also']) : null,
          )
        : _Option(option, jsString(option), null),
];

class _Segmented extends StatelessWidget {
  const _Segmented({required this.block, required this.ctx});
  final Json block;
  final _CardCtx ctx;

  @override
  Widget build(BuildContext context) {
    final key = asStr(block['bind']);
    final options = _options(block['options'], ctx);
    if (options.length < 2) return _Select(block: block, ctx: ctx);
    final current = options.indexWhere(
      (o) => jsString(o.value) == jsString(ctx.values[key]),
    );
    final label = ctx.text(block['label']);
    final off = ctx.controlsOff;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FieldLabel(label: label),
        Semantics(
          label: label,
          child: IgnorePointer(
            ignoring: off,
            child: Opacity(
              opacity: off ? 0.5 : 1,
              child: LnSegmented<int>(
                segments: [
                  for (var i = 0; i < options.length; i++)
                    LnSegment(value: i, label: options[i].label),
                ],
                selected: current < 0 ? 0 : current,
                onChanged: (i) =>
                    ctx.pick(key, options[i].value, options[i].also),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _Select extends StatefulWidget {
  const _Select({required this.block, required this.ctx});
  final Json block;
  final _CardCtx ctx;

  @override
  State<_Select> createState() => _SelectState();
}

class _SelectState extends State<_Select> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final ctx = widget.ctx;
    final ln = context.ln;
    final c = ln.colors;
    final key = asStr(widget.block['bind']);
    final options = _options(widget.block['options'], ctx);
    final chosen = options
        .where((o) => jsString(o.value) == jsString(ctx.values[key]))
        .firstOrNull;
    final label = ctx.text(widget.block['label']);
    final off = ctx.controlsOff;
    const radius = BorderRadius.all(Radius.circular(LnRadius.field));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FieldLabel(label: label),
        LnTappable(
          enabled: !off,
          onTap: () => setState(() => _open = !_open),
          semanticLabel: label,
          child: Opacity(
            opacity: off ? 0.5 : 1,
            child: Container(
              height: 48,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              decoration: BoxDecoration(
                color: c.surface,
                borderRadius: radius,
                border: Border.all(color: _open ? c.fgSubtle : c.border),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      chosen?.label ?? '',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: ln.text.body.copyWith(color: c.fg),
                    ),
                  ),
                  Icon(FIcons.chevronDown, size: 18, color: c.fgMuted),
                ],
              ),
            ),
          ),
        ),
        if (_open && !off)
          Container(
            margin: const EdgeInsets.only(top: 6),
            decoration: BoxDecoration(
              borderRadius: radius,
              border: Border.all(color: c.border),
            ),
            child: Column(
              children: [
                for (var i = 0; i < options.length; i++)
                  LnTappable(
                    onTap: () {
                      ctx.pick(key, options[i].value, options[i].also);
                      setState(() => _open = false);
                    },
                    selected: identical(options[i], chosen),
                    semanticLabel: options[i].label,
                    child: Container(
                      constraints: const BoxConstraints(minHeight: 48),
                      padding: const EdgeInsets.symmetric(horizontal: 14),
                      decoration: BoxDecoration(
                        border: i > 0
                            ? Border(top: BorderSide(color: c.border))
                            : null,
                      ),
                      child: Row(
                        children: [
                          _Radio(on: identical(options[i], chosen)),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              options[i].label,
                              style:
                                  (identical(options[i], chosen)
                                          ? ln.text.captionStrong
                                          : ln.text.caption)
                                      .copyWith(color: c.fg),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

class _Radio extends StatelessWidget {
  const _Radio({required this.on});
  final bool on;

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    return Container(
      width: 18,
      height: 18,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: on ? c.fg : c.fgSubtle, width: on ? 5.5 : 2),
      ),
    );
  }
}

class _NumberField extends StatefulWidget {
  const _NumberField({required this.block, required this.ctx});
  final Json block;
  final _CardCtx ctx;

  @override
  State<_NumberField> createState() => _NumberFieldState();
}

class _NumberFieldState extends State<_NumberField> {
  late final TextEditingController _controller = TextEditingController(
    text: _textOf(widget.ctx.values[_key]),
  );
  bool _checked = false;

  String get _key => asStr(widget.block['bind']);

  static String _textOf(Object? value) =>
      value == null ? '' : (value is num ? jsNumber(value) : '$value');

  @override
  void didUpdateWidget(_NumberField old) {
    super.didUpdateWidget(old);
    // Only an outside change (an option's `also`, a reset) replaces the owner's draft.
    final value = widget.ctx.values[_key];
    final draft = parseCardNumber(_controller.text);
    final same = draft is num && value is num ? draft == value : draft == value;
    if (!same) {
      _controller.text = _textOf(value);
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => widget.ctx.markUnreadable(_key, false),
      );
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    // A field that is hidden or removed no longer holds the send.
    final ctx = widget.ctx;
    final key = _key;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ctx.markUnreadable(key, false);
    });
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ctx = widget.ctx;
    final block = widget.block;
    final ln = context.ln;
    final c = ln.colors;
    final bad = identical(parseCardNumber(_controller.text), unreadable);
    final label = ctx.text(block['label']);
    final invalid = ctx.invalid == _key || (bad && _checked);
    Widget? affix(Object? value) => value is String
        ? Text(value, style: ln.text.caption.copyWith(color: c.fgMuted))
        : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FieldLabel(
          label: label,
          aside: block.containsKey('hint')
              ? Text(
                  ctx.text(block['hint']),
                  style: ln.text.small.copyWith(color: c.fgMuted),
                )
              : null,
        ),
        Focus(
          onFocusChange: (focused) {
            if (!focused) setState(() => _checked = true);
          },
          child: Directionality(
            // Numbers read left to right in both languages.
            textDirection: TextDirection.ltr,
            child: LnTextField(
              controller: _controller,
              focusNode: ctx.focusFor(_key),
              enabled: !ctx.controlsOff,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
                signed: true,
              ),
              textInputAction: TextInputAction.send,
              prefix: affix(block['prefix']),
              suffix: affix(block['suffix']),
              error: invalid ? '' : null,
              onChanged: (next) {
                // An unreadable draft («2,4») is never sent as a prefix value: it holds
                // the card's send until it reads as a number (review M7).
                final parsed = parseCardNumber(next);
                final unread = identical(parsed, unreadable);
                ctx.markUnreadable(_key, unread);
                if (!unread) ctx.type(_key, parsed);
                setState(() {});
              },
              onSubmitted: (_) {
                setState(() => _checked = true);
                if (!bad) ctx.submitPrimary();
              },
            ),
          ),
        ),
        if (bad && _checked)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Semantics(
              liveRegion: true,
              child: Row(
                children: [
                  Icon(FIcons.circleAlert, size: 15, color: c.error),
                  const SizedBox(width: 6),
                  Text(
                    context.t('uiInvalidValue'),
                    style: ln.text.captionStrong.copyWith(color: c.error),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class _Slider extends StatelessWidget {
  const _Slider({required this.block, required this.ctx});
  final Json block;
  final _CardCtx ctx;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final key = asStr(block['bind']);
    final min = (block['min'] is num ? block['min'] as num : 0).toDouble();
    final max = (block['max'] is num ? block['max'] as num : 100).toDouble();
    final step = block['step'] is num && (block['step'] as num) > 0
        ? (block['step'] as num).toDouble()
        : 1.0;
    final raw = toNumber(ctx.values[key] ?? min);
    final value = raw.isFinite ? raw.clamp(min, max).toDouble() : min;
    final shown = ctx.text(
      block['show'] is String ? block['show'] : '{\$$key}',
    );
    final label = ctx.text(block['label']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FieldLabel(
          label: label,
          aside: Text(
            shown,
            style: ln.text.captionStrong.copyWith(
              color: c.fg,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        RichSlider(
          value: value,
          min: min,
          max: max,
          step: step,
          label: label,
          valueLabel: shown,
          enabled: !ctx.controlsOff,
          onChanged: (next) => ctx.type(key, next),
        ),
      ],
    );
  }
}

class _CardMarkdown extends StatelessWidget {
  const _CardMarkdown({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final style = ln.text.caption.copyWith(color: c.fg);
    final blocks = cardMarkdown(text);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var b = 0; b < blocks.length; b++) ...[
          if (b > 0) const SizedBox(height: 8),
          for (var i = 0; i < blocks[b].lines.length; i++)
            Padding(
              padding: EdgeInsets.only(top: i == 0 ? 0 : 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (blocks[b].kind != 'p') ...[
                    Text(
                      blocks[b].kind == 'ul' ? '•' : '${i + 1}.',
                      style: style.copyWith(color: c.fgMuted),
                    ),
                    const SizedBox(width: 8),
                  ],
                  Expanded(child: _inline(blocks[b].lines[i], style)),
                ],
              ),
            ),
        ],
      ],
    );
  }
}

class _Note extends StatelessWidget {
  const _Note({required this.block, required this.ctx});
  final Json block;
  final _CardCtx ctx;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final tone = asString(block['tone']) ?? 'info';
    final icon =
        block['icon'] ??
        (tone == 'warn'
            ? 'alert'
            : tone == 'good'
            ? 'check'
            : 'info');
    final accent = switch (tone) {
      'warn' => c.warning,
      'good' => c.success,
      'bad' => c.error,
      _ => c.fgMuted,
    };
    final bg = switch (tone) {
      'warn' ||
      'good' ||
      'bad' => accent.withValues(alpha: c.isDark ? 0.16 : 0.1),
      _ => c.fill1,
    };
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 1),
              child: CardIcon(icon, size: 17, color: accent),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _inline(
                cardInline(ctx.text(block['text'])),
                ln.text.footnote.copyWith(color: c.fg),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.block, required this.ctx});
  final Json block;
  final _CardCtx ctx;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final trend = block.containsKey('trend')
        ? jsString(evaluate(block['trend'], ctx.env, ''))
        : '';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: c.fill1,
        borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              if (CardIcon.has(block['icon'])) ...[
                CardIcon(block['icon'], size: 14, color: c.fgMuted),
                const SizedBox(width: 4),
              ],
              Flexible(
                child: Text(
                  ctx.text(block['label']),
                  style: ln.text.small.copyWith(color: c.fgMuted),
                ),
              ),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            ctx.text(block['value']),
            style: ln.text.display.copyWith(
              color: block['tone'] == 'accent' ? c.brand : c.fg,
            ),
          ),
          if (block.containsKey('sub'))
            Row(
              children: [
                if (trend == 'up' || trend == 'down') ...[
                  Icon(
                    trend == 'down' ? FIcons.trendingDown : FIcons.trendingUp,
                    size: 14,
                    color: trend == 'down' ? c.negative : c.positive,
                  ),
                  const SizedBox(width: 3),
                ],
                Flexible(
                  child: Text(
                    ctx.text(block['sub']),
                    style: ln.text.small.copyWith(color: c.fgMuted),
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _Button extends StatelessWidget {
  const _Button({required this.block, required this.path, required this.ctx});
  final Json block;
  final String path;
  final _CardCtx ctx;

  @override
  Widget build(BuildContext context) {
    final off = _buttonOff(block, ctx);
    final primary = block['style'] == 'primary';
    return BlockButton(
      label: ctx.text(block['label']),
      variant: primary
          ? BlockButtonVariant.primary
          : BlockButtonVariant.secondary,
      onPressed: off ? null : () => ctx.act(block, path),
      expand: true,
    );
  }
}

class _Grid extends StatelessWidget {
  const _Grid({required this.block, required this.path, required this.ctx});
  final Json block;
  final String path;
  final _CardCtx ctx;

  @override
  Widget build(BuildContext context) {
    final children = asJsonList(block['children']);
    final requested = block['cols'] == 1 || block['cols'] == 3
        ? block['cols'] as int
        : 2;
    return LayoutBuilder(
      builder: (context, constraints) {
        // The columns follow the card's own width: `cols` while each cell keeps 96 dp.
        final cols = (constraints.maxWidth / 104).floor().clamp(1, requested);
        final shown = [
          for (var i = 0; i < children.length; i++)
            if (_visible(children[i], ctx.env)) i,
        ];
        final rows = <Widget>[];
        for (var r = 0; r < shown.length; r += cols) {
          rows.add(
            Padding(
              padding: EdgeInsets.only(top: r == 0 ? 0 : LnSpace.xs),
              child: IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (var k = 0; k < cols; k++) ...[
                      if (k > 0) const SizedBox(width: LnSpace.xs),
                      Expanded(
                        child: r + k < shown.length
                            ? _UiNode(
                                block: children[shown[r + k]],
                                path: '$path.${shown[r + k]}',
                                ctx: ctx,
                              )
                            : const SizedBox.shrink(),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: rows,
        );
      },
    );
  }
}

class _More extends StatelessWidget {
  const _More({required this.block, required this.path, required this.ctx});
  final Json block;
  final String path;
  final _CardCtx ctx;

  @override
  Widget build(BuildContext context) {
    final id = '${ctx.cardKey}:$path';
    if (_openedMore.contains(id)) {
      return _Children(block: block, path: path, ctx: ctx, gap: 12);
    }
    final ln = context.ln;
    final label = block['label'] is String
        ? ctx.text(block['label'])
        : context.t('uiShowMore');
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: LnTappable(
        onTap: () {
          _openedMore.add(id);
          ctx.redraw();
        },
        semanticLabel: label,
        excludeChildSemantics: true,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 48),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                label,
                style: ln.text.captionStrong.copyWith(color: ln.colors.fgMuted),
              ),
              const SizedBox(width: 4),
              Icon(FIcons.chevronDown, size: 16, color: ln.colors.fgMuted),
            ],
          ),
        ),
      ),
    );
  }
}

/// A trusted slot (mandate 10.2): the live fixed card inside a frame no agent node can draw.
class _Slot extends StatelessWidget {
  const _Slot({required this.block, required this.ctx});
  final Json block;
  final _CardCtx ctx;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final frame = Color.lerp(c.brand, c.fgSubtle, 0.45)!;
    final inner = buildSlotCard(
      context,
      threadId: ctx.threadId,
      card: asStr(block['card']),
      record: asStr(block['record']),
    );
    return Semantics(
      container: true,
      label: context.t('uiSlotMark'),
      child: Container(
        padding: const EdgeInsets.all(LnSpace.xs),
        decoration: BoxDecoration(
          color: c.brand.withValues(alpha: 0.06),
          borderRadius: const BorderRadius.all(
            Radius.circular(LnRadius.card - 4),
          ),
          border: Border.all(color: frame, width: 3),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(4, 2, 4, 8),
              child: Row(
                children: [
                  CardIcon('shield', size: 14, color: frame),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      context.t('uiSlotMark'),
                      style: ln.text.smallStrong.copyWith(color: frame),
                    ),
                  ),
                ],
              ),
            ),
            inner,
          ],
        ),
      ),
    );
  }
}

class _Delivery extends StatelessWidget {
  const _Delivery({required this.block});
  final Json block;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    const labels = {
      'app': 'uiDeliveryApp',
      'push': 'uiDeliveryPush',
      'call': 'uiDeliveryCall',
    };
    final channels = asStringList(block['channels']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _FieldLabel(label: context.t('uiDelivery')),
        Container(
          decoration: BoxDecoration(
            borderRadius: const BorderRadius.all(
              Radius.circular(LnRadius.field),
            ),
            border: Border.all(color: c.border),
          ),
          child: Column(
            children: [
              for (var i = 0; i < channels.length; i++)
                Semantics(
                  checked: true,
                  enabled: false,
                  child: Container(
                    constraints: const BoxConstraints(minHeight: 44),
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    decoration: BoxDecoration(
                      border: i > 0
                          ? Border(top: BorderSide(color: c.border))
                          : null,
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 22,
                          height: 22,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: c.fg,
                            borderRadius: const BorderRadius.all(
                              Radius.circular(7),
                            ),
                          ),
                          child: Icon(FIcons.check, size: 14, color: c.bg),
                        ),
                        const SizedBox(width: 10),
                        Text(
                          context.t(labels[channels[i]] ?? 'uiDeliveryApp'),
                          style: ln.text.captionStrong.copyWith(color: c.fg),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class _Skeleton extends StatelessWidget {
  const _Skeleton();

  @override
  Widget build(BuildContext context) {
    final c = context.ln.colors;
    Widget bar(double factor) => FractionallySizedBox(
      alignment: AlignmentDirectional.centerStart,
      widthFactor: factor,
      child: Container(
        height: 13,
        decoration: BoxDecoration(
          color: c.fill4,
          borderRadius: const BorderRadius.all(Radius.circular(7)),
        ),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [bar(1), const SizedBox(height: 8), bar(0.62)],
    );
  }
}

class _Footer extends StatelessWidget {
  const _Footer({
    required this.locked,
    required this.cut,
    required this.why,
    required this.whyOpen,
    required this.agentName,
    required this.oldest,
    required this.onWhy,
    required this.onUnlock,
  });

  final bool locked;
  final bool cut;
  final String? why;
  final bool whyOpen;
  final String? agentName;
  final DateTime? oldest;
  final VoidCallback onWhy;
  final VoidCallback? onUnlock;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final small = ln.text.smallStrong;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(height: 1, color: c.border),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            LnSpace.cardPadding,
            4,
            LnSpace.xs,
            4,
          ),
          child: Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: LnSpace.sm,
            children: [
              if (locked) ...[
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(FIcons.checkCheck, size: 15, color: c.fg),
                    const SizedBox(width: 5),
                    Text(
                      context.t('uiSentTo', [agentName ?? 'Lonora']),
                      style: small.copyWith(color: c.fg),
                    ),
                  ],
                ),
                if (onUnlock != null)
                  LnTappable(
                    onTap: onUnlock,
                    semanticLabel: context.t('uiEdit'),
                    excludeChildSemantics: true,
                    child: SizedBox(
                      height: 48,
                      child: Center(
                        widthFactor: 1,
                        child: Text(
                          context.t('uiEdit'),
                          style: small.copyWith(
                            color: c.fg,
                            decoration: TextDecoration.underline,
                            decorationColor: c.fg,
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
              if (cut)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(FIcons.circleStop, size: 15, color: c.fgMuted),
                    const SizedBox(width: 5),
                    Flexible(
                      child: Text(
                        context.t('uiCut'),
                        style: small.copyWith(color: c.fgMuted),
                      ),
                    ),
                  ],
                ),
              if (why != null)
                LnTappable(
                  onTap: onWhy,
                  selected: whyOpen,
                  semanticLabel: context.t('uiWhy'),
                  excludeChildSemantics: true,
                  child: SizedBox(
                    height: 48,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(FIcons.sparkles, size: 14, color: c.brand),
                        const SizedBox(width: 5),
                        Text(
                          context.t('uiWhy'),
                          style: ln.text.small.copyWith(
                            color: whyOpen ? c.fg : c.fgMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
        if (why != null && whyOpen)
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              LnSpace.cardPadding,
              0,
              LnSpace.cardPadding,
              LnSpace.sm,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(why!, style: ln.text.footnote.copyWith(color: c.fgMuted)),
                // When the card's facts were read; never the tools' internal names.
                if (oldest != null)
                  Text(
                    '${context.t('uiLastUpdated')} ${clockTime(oldest!, lang: context.l10n.lang)}',
                    style: ln.text.small.copyWith(color: c.fgMuted),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}
