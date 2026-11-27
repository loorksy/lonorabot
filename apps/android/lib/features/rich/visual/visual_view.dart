// Legacy v1 visual documents (`rich_content` parts written before lonora-ui v2), drawn
// natively with the Lonora kit: the twin of apps/mobile/components/native-rich-response.tsx
// `NativeVisualDocument` and native-rich-graphics.tsx. Only rendered: their local control
// state lives in memory for this run of the app. Actions: `follow_up` sends the owner's text
// through the thread's send path, `open_chart` / `open_artifact` navigate.
import 'dart:math' as math;

import 'package:async_redux/async_redux.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;
import 'package:go_router/go_router.dart';

import '../../../app/routes.dart';
import '../../../core/api/api_error.dart';
import '../../../core/json.dart';
import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../../../state/actions/thread_actions.dart';
import '../artifact_image.dart';
import '../rich_slider.dart';
import 'visual_document.dart';

/// Local state of the documents drawn this session, so a list redraw keeps the owner's
/// choices (Expo keeps them in files; Android keeps them for the app's lifetime).
final Map<String, (VisualState, Map<String, bool>)> _states = {};

class VisualDocumentView extends StatefulWidget {
  const VisualDocumentView({
    super.key,
    required this.document,
    required this.threadId,
    this.messageId,
    this.index = 0,
  });

  final Json document;
  final String threadId;
  final String? messageId;
  final int index;

  @override
  State<VisualDocumentView> createState() => _VisualDocumentViewState();
}

class _VisualDocumentViewState extends State<VisualDocumentView> {
  late VisualState _state;
  late Map<String, bool> _expanded;
  String? _pending;
  String? _error;

  String get _key =>
      '${widget.threadId}:${widget.messageId ?? 'preview'}:${widget.index}';

  @override
  void initState() {
    super.initState();
    final saved = _states[_key];
    _state = initialVisualState(widget.document, saved?.$1);
    _expanded = {...?saved?.$2};
  }

  void _save() {
    _states.remove(_key);
    _states[_key] = (_state, _expanded);
    if (_states.length > 200) _states.remove(_states.keys.first);
  }

  Json get _doc => widget.document;

  Object? _value(Object? raw) => evaluateVisualValue(raw, _doc, _state);

  String _print(Object? raw) => visualPrint(
    raw,
    unavailable: context.t('visualUnavailable'),
    yes: context.t('visualTrue'),
    no: context.t('visualFalse'),
  );

  void _change(String nodeId, Object? next) {
    setState(() {
      _state = updateVisualState(_doc, _state, nodeId, next);
      _save();
    });
  }

  Future<void> _act(Json node, Json? action) async {
    if (_pending != null) return;
    final next = expandVisualAction(action, _doc, _state);
    if (next == null) {
      setState(() => _error = context.t('visualActionUnavailable'));
      return;
    }
    final router = GoRouter.maybeOf(context);
    setState(() {
      _pending = asStr(node['id']);
      _error = null;
    });
    try {
      switch (next['kind']) {
        case 'follow_up':
          await context.dispatchAndWait(
            SendMessageAction(widget.threadId, {
              'content': asStr(next['text']),
            }),
          );
        case 'open_chart':
          await router?.push(
            Routes.charts(
              threadId: widget.threadId,
              chartId: asStr(next['resource_id']),
            ),
          );
        case 'open_artifact':
          await router?.push(Routes.artifact(asStr(next['resource_id'])));
      }
    } on ApiError catch (e) {
      if (mounted) setState(() => _error = context.l10n.errorText(e.code));
    } finally {
      if (mounted) setState(() => _pending = null);
    }
  }

  Color _tone(Object? tone) {
    final c = context.ln.colors;
    return switch (tone) {
      'info' => c.selection,
      'success' => c.success,
      'warning' => c.warning,
      'danger' => c.error,
      _ => c.fg,
    };
  }

  double _gap(Object? gap) => switch (gap) {
    'small' => LnSpace.xs,
    'large' => LnSpace.lg,
    _ => LnSpace.sm,
  };

  Widget? _label(Object? text) {
    if (text is! String || text.isEmpty) return null;
    final ln = context.ln;
    return Text(
      text,
      style: ln.text.captionStrong.copyWith(color: ln.colors.fg),
    );
  }

  BoxDecoration get _frame => BoxDecoration(
    color: context.ln.colors.fill1,
    borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
  );

  Widget _column(List<Widget> children, double gap) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    mainAxisSize: MainAxisSize.min,
    children: [
      for (var i = 0; i < children.length; i++) ...[
        if (i > 0) SizedBox(height: gap),
        children[i],
      ],
    ],
  );

  List<Widget> _children(Json node) => [
    for (final child in asJsonList(node['children'])) ?_node(child),
  ];

  Widget? _node(Json node) {
    if (node.containsKey('visible')) {
      final v = _value(node['visible']);
      if (v == null || v == false || v == 0 || v == '') return null;
    }
    final ln = context.ln;
    final c = ln.colors;
    final color = _tone(node['tone']);
    // Q7: green set as text takes the text-safe ink; icons and fills keep the tone.
    final ink = node['tone'] == 'success' ? c.successText : color;
    final gap = _gap(node['gap']);
    final body = ln.text.caption.copyWith(color: ink);
    switch (asStr(node['type'])) {
      case 'text':
        return Text(
          asString(node['text']) ?? _print(_value(node['value'])),
          style: body,
        );
      case 'heading':
        final level = asInt(node['level']) ?? 2;
        final style = switch (level) {
          1 => ln.text.display,
          2 => ln.text.headline,
          _ => ln.text.title.copyWith(fontWeight: FontWeight.w600),
        };
        return Semantics(
          header: true,
          child: Text(asStr(node['text']), style: style.copyWith(color: ink)),
        );
      case 'badge':
        return Align(
          alignment: AlignmentDirectional.centerStart,
          child: StatusChip(
            label: asString(node['text']) ?? _print(_value(node['value'])),
            kind: switch (node['tone']) {
              'success' => StatusChipKind.success,
              'warning' => StatusChipKind.waiting,
              'danger' => StatusChipKind.error,
              'info' => StatusChipKind.running,
              _ => StatusChipKind.neutral,
            },
          ),
        );
      case 'icon':
        return Align(
          alignment: AlignmentDirectional.centerStart,
          child: Icon(_icon(asStr(node['text'])), size: 24, color: color),
        );
      case 'divider':
        return Container(height: 1, color: c.border);
      case 'metric':
        final unit = node.containsKey('unit')
            ? ' ${_print(_value(node['unit']))}'
            : '';
        return Container(
          padding: const EdgeInsets.all(LnSpace.sm),
          decoration: _frame,
          child: _column([
            ?_label(node['label']),
            Text(
              '${_print(_value(node['value']))}$unit',
              style: ln.text.display.copyWith(color: ink),
            ),
          ], 4),
        );
      case 'column' || 'container':
        return _column([?_label(node['label']), ..._children(node)], gap);
      case 'card' || 'form':
        return Container(
          padding: const EdgeInsets.all(LnSpace.sm),
          decoration: _frame,
          child: _column([?_label(node['label']), ..._children(node)], gap),
        );
      case 'row':
        final kids = _children(node);
        return LayoutBuilder(
          builder: (context, constraints) {
            if (kids.length <= 3 && constraints.maxWidth / kids.length >= 96) {
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (var i = 0; i < kids.length; i++) ...[
                    if (i > 0) SizedBox(width: gap),
                    Expanded(child: kids[i]),
                  ],
                ],
              );
            }
            return _column(kids, gap);
          },
        );
      case 'grid':
        final kids = _children(node);
        final requested = asInt(node['columns']) ?? 2;
        return LayoutBuilder(
          builder: (context, constraints) {
            final cols = ((constraints.maxWidth + gap) / (120 + gap))
                .floor()
                .clamp(1, requested);
            return _column([
              for (var r = 0; r < kids.length; r += cols)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (var k = 0; k < cols; k++) ...[
                      if (k > 0) SizedBox(width: gap),
                      Expanded(
                        child: r + k < kids.length
                            ? kids[r + k]
                            : const SizedBox.shrink(),
                      ),
                    ],
                  ],
                ),
            ], gap);
          },
        );
      case 'list' || 'timeline':
        final kids = asJsonList(node['children']);
        return _column([
          ?_label(node['label']),
          for (var i = 0; i < kids.length; i++)
            if (_node(kids[i]) case final child?)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ConstrainedBox(
                    constraints: const BoxConstraints(minWidth: 16),
                    child: Text(
                      node['type'] == 'timeline' ? '${i + 1}' : '•',
                      style: ln.text.caption.copyWith(color: c.fgMuted),
                    ),
                  ),
                  const SizedBox(width: LnSpace.sm),
                  Expanded(child: child),
                ],
              ),
        ], gap);
      case 'progress':
        final observed = _value(node['value']);
        final maximum = (node['maximum'] as num?) ?? 100;
        final number = observed is num ? observed : double.nan;
        final ratio = number.isFinite && maximum > 0
            ? (number / maximum).clamp(0.0, 1.0)
            : null;
        return _column([
          ?_label(node['label']),
          Text(_print(observed), style: body),
          if (ratio != null)
            Semantics(
              value: _print(observed),
              child: ClipRRect(
                borderRadius: const BorderRadius.all(Radius.circular(4)),
                child: SizedBox(
                  height: 8,
                  child: Stack(
                    children: [
                      Positioned.fill(child: ColoredBox(color: c.fill4)),
                      FractionallySizedBox(
                        alignment: AlignmentDirectional.centerStart,
                        widthFactor: ratio.toDouble(),
                        child: ColoredBox(color: color),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ], LnSpace.xs);
      case 'table':
        return _table(node);
      case 'chart':
        return _VisualChart(
          node: node,
          points: [
            for (final p in asJsonList(node['points']))
              (
                _print(_value(p['label'])),
                _value(p['value']) is num ? _value(p['value']) as num : null,
              ),
          ],
          unavailable: context.t('visualUnavailable'),
        );
      case 'diagram':
        return _VisualDiagram(node: node);
      case 'image':
        final id = asString(node['artifact_id']);
        return id == null
            ? null
            : ArtifactImage(artifactId: id, label: asString(node['label']));
      case 'disclosure':
        final id = asStr(node['id']);
        final open = _expanded[id] ?? false;
        final label = asString(node['label']) ?? context.t('visualDetails');
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: LnSpace.sm),
          decoration: _frame,
          child: _column([
            LnTappable(
              onTap: () => setState(() {
                _expanded = {..._expanded, id: !open};
                _save();
              }),
              selected: open,
              semanticLabel: label,
              excludeChildSemantics: true,
              child: SizedBox(
                height: 48,
                child: Row(
                  children: [
                    Expanded(child: _label(label)!),
                    Icon(
                      open ? FIcons.chevronUp : FIcons.chevronDown,
                      size: 18,
                      color: c.fgMuted,
                    ),
                  ],
                ),
              ),
            ),
            if (open) ..._children(node),
            if (open) const SizedBox(height: LnSpace.xxs),
          ], LnSpace.xs),
        );
      case 'tabs' || 'select':
        final options = asJsonList(node['options']);
        final key = asStr(node['state_key']);
        final selected =
            '${_state[key] ?? (options.isEmpty ? '' : options.first['value'])}';
        final index = math.max(
          0,
          options.indexWhere((o) => o['value'] == selected),
        );
        final kids = asJsonList(node['children']);
        return _column([
          ?_label(node['label']),
          // Each chip's 48 dp hit area includes half the 8 dp gap above and below it.
          Wrap(
            spacing: LnSpace.xs,
            children: [
              for (final option in options)
                _Choice(
                  label: asStr(option['label']),
                  selected: option['value'] == selected,
                  onTap: () => _change(asStr(node['id']), option['value']),
                ),
            ],
          ),
          if (node['type'] == 'tabs' && index < kids.length)
            ?_node(kids[index]),
        ], LnSpace.sm);
      case 'checkbox':
        final key = asStr(node['state_key']);
        return Row(
          children: [
            Expanded(child: _label(node['label']) ?? const SizedBox.shrink()),
            LnSwitch(
              value: _state[key] == true,
              semanticLabel: asString(node['label']) ?? asStr(node['id']),
              onChanged: (next) => _change(asStr(node['id']), next),
            ),
          ],
        );
      case 'input':
        return _VisualInput(
          node: node,
          value: _state[asStr(node['state_key'])],
          onChanged: (next) => _change(asStr(node['id']), next),
        );
      case 'slider':
        final key = asStr(node['state_key']);
        final min = ((node['minimum'] as num?) ?? 0).toDouble();
        final max = ((node['maximum'] as num?) ?? 100).toDouble();
        final value = (_state[key] is num ? _state[key] as num : min)
            .toDouble();
        final label = asStr(node['label']);
        return _column([
          Row(
            children: [
              Expanded(child: _label(label) ?? const SizedBox.shrink()),
              Text(
                _print(_state[key]),
                style: ln.text.captionStrong.copyWith(color: c.fg),
              ),
            ],
          ),
          RichSlider(
            value: value,
            min: min,
            max: max,
            step: ((node['step'] as num?) ?? 1).toDouble(),
            label: label,
            valueLabel: _print(_state[key]),
            onChanged: (next) => _change(asStr(node['id']), next),
          ),
        ], 0);
      case 'button':
        final action = node['action'] is Map ? asJson(node['action']) : null;
        return BlockButton(
          label: asStr(node['label']),
          loading: _pending == asStr(node['id']),
          onPressed: _pending != null ? null : () => _act(node, action),
        );
    }
    return null;
  }

  Widget _table(Json node) {
    final ln = context.ln;
    final c = ln.colors;
    final fields = asJsonList(node['fields']);
    final rows = filterVisualRows(node, _doc, _state);
    final filterKey = asString(node['filter_key']);
    Widget cell(String text, {bool head = false}) => SizedBox(
      width: 145,
      child: Padding(
        padding: const EdgeInsets.all(LnSpace.sm),
        child: Text(
          text,
          style: (head ? ln.text.captionStrong : ln.text.caption).copyWith(
            color: c.fg,
          ),
        ),
      ),
    );
    return _column([
      ?_label(node['label']),
      if (filterKey != null)
        LnTextField(
          hint: context.t('visualFilter'),
          onChanged: (next) => _change(asStr(node['id']), next),
        ),
      DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: const BorderRadius.all(Radius.circular(LnRadius.field)),
          border: Border.all(color: c.border),
        ),
        child: ClipRRect(
          borderRadius: const BorderRadius.all(
            Radius.circular(LnRadius.field - 1),
          ),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ColoredBox(
                  color: c.fill2,
                  child: Row(
                    children: [
                      for (final f in fields)
                        cell(asStr(f['label']), head: true),
                    ],
                  ),
                ),
                for (final row in rows)
                  DecoratedBox(
                    decoration: BoxDecoration(
                      border: Border(top: BorderSide(color: c.border)),
                    ),
                    child: Row(
                      children: [
                        for (final f in fields)
                          cell(_print(_value(row[asStr(f['key'])]))),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    ], LnSpace.xs);
  }

  IconData _icon(String name) => switch (name) {
    'call' => FIcons.phone,
    'mic' => FIcons.mic,
    'search' => FIcons.search,
    'layers' => FIcons.layers,
    'plus' => FIcons.plus,
    'back' => FIcons.arrowLeft,
    'chevron' => FIcons.chevronRight,
    'chart' => FIcons.chartColumn,
    'send' => FIcons.send,
    'close' => FIcons.x,
    'file' => FIcons.file,
    'clock' => FIcons.clock,
    'settings' => FIcons.settings,
    'group' => FIcons.users,
    'agent' => FIcons.bot,
    'download' => FIcons.download,
    'check' => FIcons.check,
    'stop' => FIcons.circleStop,
    'refresh' => FIcons.refreshCw,
    'globe' => FIcons.globe,
    _ => FIcons.activity,
  };

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final mode = asStr(_doc['mode']);
    final observed = {
      for (final fact in asJson(_doc['facts']).values)
        ?asString(asJson(fact)['observed_at']),
    };
    final root = _node(asJson(_doc['root']));
    return Container(
      padding: const EdgeInsets.all(LnSpace.cardPadding),
      child: _column([
        if (mode != 'observed')
          Text(
            context.t(mode == 'example' ? 'visualExample' : 'visualEstimate'),
            style: ln.text.small.copyWith(
              color: mode == 'estimate' ? c.warning : c.fgMuted,
            ),
          ),
        ?root,
        for (final time in observed)
          Text(
            '${context.t('visualObservedAt')}: '
            '${DateTime.tryParse(time) == null ? context.t('visualUnavailable') : formatDate('yMd jm', context.l10n.lang, DateTime.parse(time).toLocal())}',
            style: ln.text.small.copyWith(color: c.fgMuted),
          ),
        if (_error != null)
          Semantics(
            liveRegion: true,
            child: Text(
              _error!,
              style: ln.text.footnote.copyWith(color: c.error),
            ),
          ),
      ], LnSpace.sm),
    );
  }
}

class _Choice extends StatelessWidget {
  const _Choice({
    required this.label,
    required this.selected,
    required this.onTap,
  });
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    return LnTappable(
      onTap: onTap,
      haptic: true,
      selected: selected,
      semanticLabel: label,
      excludeChildSemantics: true,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: LnSpace.xs / 2),
        child: Container(
          constraints: const BoxConstraints(minHeight: 40, minWidth: 48),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: ShapeDecoration(
            color: selected ? c.fgStrong : c.fill3,
            shape: const StadiumBorder(),
          ),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: ln.text.captionStrong.copyWith(
              color: selected ? c.bg : c.fg,
            ),
          ),
        ),
      ),
    );
  }
}

class _VisualInput extends StatefulWidget {
  const _VisualInput({
    required this.node,
    required this.value,
    required this.onChanged,
  });
  final Json node;
  final Object? value;
  final ValueChanged<Object?> onChanged;

  @override
  State<_VisualInput> createState() => _VisualInputState();
}

class _VisualInputState extends State<_VisualInput> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.value == null ? '' : '${widget.value}',
  );

  bool get _number => widget.node['input_kind'] == 'number';

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final field = LnTextField(
      controller: _controller,
      label: asString(widget.node['label']),
      keyboardType: _number
          ? const TextInputType.numberWithOptions(decimal: true, signed: true)
          : TextInputType.text,
      onChanged: (text) {
        if (!_number) {
          widget.onChanged(text);
          return;
        }
        // Arabic-Indic digits and the Arabic decimal sign read as numbers; an unfinished
        // draft keeps its text without changing the state.
        final normalized = text
            .trim()
            .replaceAllMapped(
              RegExp('[٠-٩]'),
              (m) => '${'٠١٢٣٤٥٦٧٨٩'.indexOf(m[0]!)}',
            )
            .replaceAllMapped(
              RegExp('[۰-۹]'),
              (m) => '${'۰۱۲۳۴۵۶۷۸۹'.indexOf(m[0]!)}',
            )
            .replaceAll('٫', '.')
            .replaceAll('٬', '');
        if (normalized.isEmpty) {
          widget.onChanged(null);
        } else if (double.tryParse(normalized) case final n?) {
          widget.onChanged(n);
        }
      },
    );
    return _number
        ? Directionality(textDirection: TextDirection.ltr, child: field)
        : field;
  }
}

class _VisualChart extends StatelessWidget {
  const _VisualChart({
    required this.node,
    required this.points,
    required this.unavailable,
  });

  final Json node;
  final List<(String, num?)> points;
  final String unavailable;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final kind = asStr(node['chart_kind'], 'line');
    final values = points.where((p) => p.$2 != null).toList();
    final tones = [
      c.selection,
      c.success,
      c.warning,
      c.brand,
      c.error,
      c.fgMuted,
    ];
    Widget chart;
    if (values.isEmpty) {
      chart = Center(
        child: Text(
          unavailable,
          style: ln.text.caption.copyWith(color: c.fgMuted),
        ),
      );
    } else if (kind == 'pie') {
      chart = PieChart(
        PieChartData(
          sectionsSpace: 2,
          centerSpaceRadius: 36,
          sections: [
            for (var i = 0; i < values.length; i++)
              PieChartSectionData(
                value: values[i].$2!.abs().toDouble(),
                color: tones[i % tones.length],
                radius: 48,
                showTitle: false,
              ),
          ],
        ),
      );
    } else {
      final minY = math
          .min(0, values.map((p) => p.$2!).reduce(math.min))
          .toDouble();
      final maxY = math
          .max(0, values.map((p) => p.$2!).reduce(math.max))
          .toDouble();
      final grid = FlGridData(
        drawVerticalLine: false,
        getDrawingHorizontalLine: (_) =>
            FlLine(color: c.border, strokeWidth: 1),
      );
      final titles = FlTitlesData(
        topTitles: const AxisTitles(),
        rightTitles: const AxisTitles(),
        leftTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 40,
            getTitlesWidget: (v, meta) => Text(
              meta.formattedValue,
              style: ln.text.small.copyWith(color: c.fgMuted),
            ),
          ),
        ),
        bottomTitles: const AxisTitles(),
      );
      chart = Directionality(
        textDirection: TextDirection.ltr,
        child: kind == 'bar'
            ? BarChart(
                BarChartData(
                  minY: minY,
                  maxY: maxY == minY ? minY + 1 : maxY,
                  gridData: grid,
                  borderData: FlBorderData(show: false),
                  titlesData: titles,
                  barTouchData: BarTouchData(enabled: false),
                  barGroups: [
                    for (var i = 0; i < values.length; i++)
                      BarChartGroupData(
                        x: i,
                        barRods: [
                          BarChartRodData(
                            toY: values[i].$2!.toDouble(),
                            color: values[i].$2! < 0 ? c.negative : c.selection,
                            width: 14,
                            borderRadius: const BorderRadius.all(
                              Radius.circular(2),
                            ),
                          ),
                        ],
                      ),
                  ],
                ),
              )
            : LineChart(
                LineChartData(
                  minY: minY,
                  maxY: maxY == minY ? minY + 1 : maxY,
                  gridData: grid,
                  borderData: FlBorderData(show: false),
                  titlesData: titles,
                  lineTouchData: const LineTouchData(enabled: false),
                  lineBarsData: [
                    LineChartBarData(
                      spots: [
                        for (var i = 0; i < values.length; i++)
                          FlSpot(i.toDouble(), values[i].$2!.toDouble()),
                      ],
                      color: c.selection,
                      barWidth: 2,
                      dotData: const FlDotData(show: false),
                    ),
                  ],
                ),
              ),
      );
    }
    final label = asString(node['label']);
    return Semantics(
      label: [
        ?label,
        for (final p in points) '${p.$1}: ${p.$2 ?? unavailable}',
      ].join('. '),
      child: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (label != null) ...[
              Text(label, style: ln.text.captionStrong.copyWith(color: c.fg)),
              const SizedBox(height: LnSpace.xs),
            ],
            SizedBox(height: 200, child: chart),
            const SizedBox(height: LnSpace.xs),
            Wrap(
              spacing: LnSpace.sm,
              runSpacing: 4,
              children: [
                for (var i = 0; i < points.length; i++)
                  Text(
                    '${points[i].$1}: ${points[i].$2 == null ? unavailable : jsNumberText(points[i].$2!)}',
                    style: ln.text.small.copyWith(
                      color: kind == 'pie'
                          ? tones[i % tones.length]
                          : c.fgMuted,
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

String jsNumberText(num v) =>
    v == v.truncateToDouble() && v.abs() < 1e15 ? '${v.toInt()}' : '$v';

class _VisualDiagram extends StatelessWidget {
  const _VisualDiagram({required this.node});
  final Json node;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final vertices = asJsonList(node['vertices']);
    final edges = asJsonList(node['edges']);
    final rtl = Directionality.of(context) == TextDirection.rtl;
    if (vertices.isEmpty) {
      return Text(
        context.t('visualUnavailable'),
        style: ln.text.caption.copyWith(color: c.fgMuted),
      );
    }
    String labelOf(String id) =>
        asStr(vertices.where((v) => v['id'] == id).firstOrNull?['label']);
    final label = asString(node['label']);
    return Semantics(
      label: [
        ?label,
        for (final v in vertices) asStr(v['label']),
        for (final e in edges)
          '${labelOf(asStr(e['source']))} → ${labelOf(asStr(e['target']))}',
      ].join('. '),
      child: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (label != null) ...[
              Text(label, style: ln.text.captionStrong.copyWith(color: c.fg)),
              const SizedBox(height: LnSpace.xs),
            ],
            LayoutBuilder(
              builder: (context, constraints) {
                final width = constraints.maxWidth;
                final columns = width > 500 ? 3 : 2;
                const pad = LnSpace.md;
                final boxWidth = math.max(
                  100.0,
                  (width - pad * (columns + 1)) / columns,
                );
                const boxHeight = 64.0;
                const rowHeight = boxHeight + LnSpace.lg * 2;
                final height = (vertices.length / columns).ceil() * rowHeight;
                Offset at(String id) {
                  final i = vertices.indexWhere((v) => v['id'] == id);
                  final col = rtl ? columns - 1 - i % columns : i % columns;
                  return Offset(
                    pad + col * (boxWidth + pad),
                    pad + (i ~/ columns) * rowHeight,
                  );
                }

                return SizedBox(
                  height: height,
                  child: Stack(
                    children: [
                      Positioned.fill(
                        child: CustomPaint(
                          painter: _EdgePainter(
                            edges: [
                              for (final e in edges)
                                (
                                  at(asStr(e['source'])),
                                  at(asStr(e['target'])),
                                  asString(e['label']),
                                ),
                            ],
                            box: Size(boxWidth, boxHeight),
                            color: c.fgMuted,
                            labelStyle: ln.text.small.copyWith(
                              color: c.fgMuted,
                            ),
                          ),
                        ),
                      ),
                      for (final v in vertices)
                        Positioned(
                          left: at(asStr(v['id'])).dx,
                          top: at(asStr(v['id'])).dy,
                          width: boxWidth,
                          height: boxHeight,
                          child: Container(
                            alignment: Alignment.center,
                            padding: const EdgeInsets.symmetric(horizontal: 8),
                            decoration: BoxDecoration(
                              color: c.surface,
                              borderRadius: const BorderRadius.all(
                                Radius.circular(LnRadius.field),
                              ),
                              border: Border.all(color: c.border),
                            ),
                            child: Text(
                              asStr(v['label']),
                              maxLines: 3,
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.center,
                              style: ln.text.small.copyWith(color: c.fg),
                            ),
                          ),
                        ),
                    ],
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _EdgePainter extends CustomPainter {
  _EdgePainter({
    required this.edges,
    required this.box,
    required this.color,
    required this.labelStyle,
  });
  final List<(Offset, Offset, String?)> edges;
  final Size box;
  final Color color;
  final TextStyle labelStyle;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1;
    for (final (from, to, label) in edges) {
      final sameRow = from.dy == to.dy;
      final forward = from.dx < to.dx;
      final down = from.dy < to.dy;
      final p1 = sameRow
          ? Offset(
              from.dx + (forward ? box.width : 0),
              from.dy + box.height / 2,
            )
          : Offset(from.dx + box.width / 2, from.dy + (down ? box.height : 0));
      final p2 = sameRow
          ? Offset(to.dx + (forward ? 0 : box.width), to.dy + box.height / 2)
          : Offset(to.dx + box.width / 2, to.dy + (down ? 0 : box.height));
      canvas.drawLine(p1, p2, paint);
      final angle = math.atan2(p2.dy - p1.dy, p2.dx - p1.dx);
      final arrow = Path()
        ..moveTo(p2.dx, p2.dy)
        ..lineTo(
          p2.dx - 7 * math.cos(angle) + 4 * math.sin(angle),
          p2.dy - 7 * math.sin(angle) - 4 * math.cos(angle),
        )
        ..lineTo(
          p2.dx - 7 * math.cos(angle) - 4 * math.sin(angle),
          p2.dy - 7 * math.sin(angle) + 4 * math.cos(angle),
        )
        ..close();
      canvas.drawPath(arrow, Paint()..color = color);
      if (label != null && label.isNotEmpty) {
        final tp = TextPainter(
          text: TextSpan(
            text: label.length > 25 ? label.substring(0, 25) : label,
            style: labelStyle,
          ),
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: 160);
        tp.paint(canvas, Offset((p1.dx + p2.dx) / 2 + 4, (p1.dy + p2.dy) / 2));
      }
    }
  }

  @override
  bool shouldRepaint(_EdgePainter old) => true;
}
