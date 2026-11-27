// Port of the v1 half of packages/core/src/visual-response.ts: fail-closed validation of stored
// `VisualDocument`s (version 1, messages written before lonora-ui v2), their bounded value
// expressions, the local control state and action expansion. Nothing is executed; no action
// is a URL or a broker call.
import 'dart:convert';
import 'dart:math' as math;

import '../../../core/json.dart';

const int maxVisualBytes = 64000;
const int maxVisualNodes = 120;
const int maxVisualDepth = 10;

final RegExp _keyPattern = RegExp(r'^[A-Za-z][A-Za-z0-9_-]{0,47}$');
final RegExp resourcePattern = RegExp(
  r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$',
  caseSensitive: false,
);

bool _isKey(Object? value) =>
    value is String &&
    _keyPattern.hasMatch(value) &&
    !const ['constructor', 'prototype', '__proto__'].contains(value);

bool isVisualScalar(Object? value) =>
    value == null ||
    value is String ||
    value is bool ||
    (value is num && value.isFinite);

bool _hasPlaceholder(Object? value) => value is String && value.contains('{{');

bool _text(Object? value, int maximum, [bool nullable = false]) =>
    (nullable && value == null) ||
    (value is String && value.length <= maximum && !_hasPlaceholder(value));

bool _literal(Object? value, List<String> choices) =>
    value is String && choices.contains(value);

bool _fieldsOnly(Map value, List<String> fields) =>
    value.keys.every(fields.contains);

bool _array(Object? value, int maximum) =>
    value is List && value.length <= maximum;

bool _numeric(
  Object? value, [
  num minimum = double.negativeInfinity,
  num maximum = double.infinity,
]) => value is num && value.isFinite && value >= minimum && value <= maximum;

bool _int(Object? value) => value is num && value == value.truncateToDouble();

const _common = ['id', 'type', 'visible', 'tone'];
const _layout = ['children', 'label', 'gap'];
const Map<String, List<String>> _allowed = {
  'column': _layout,
  'row': _layout,
  'container': _layout,
  'card': _layout,
  'list': _layout,
  'timeline': _layout,
  'disclosure': _layout,
  'form': _layout,
  'grid': ['children', 'columns', 'gap'],
  'divider': [],
  'text': ['text', 'value'],
  'heading': ['text', 'level'],
  'badge': ['text', 'value'],
  'icon': ['text'],
  'metric': ['label', 'value', 'unit'],
  'table': ['label', 'fields', 'rows', 'filter_key'],
  'progress': ['label', 'value', 'maximum'],
  'diagram': ['label', 'vertices', 'edges'],
  'chart': ['label', 'chart_kind', 'points'],
  'image': ['artifact_id', 'label'],
  'tabs': ['children', 'options', 'state_key'],
  'button': ['label', 'action'],
  'select': ['label', 'options', 'state_key'],
  'checkbox': ['label', 'state_key'],
  'slider': ['label', 'state_key', 'minimum', 'maximum', 'step'],
  'input': ['label', 'state_key', 'input_kind', 'minimum', 'maximum', 'step'],
};
const Map<String, (int, int)> _operatorArity = {
  'add': (1, 8),
  'sub': (2, 2),
  'mul': (1, 8),
  'div': (2, 2),
  'min': (1, 8),
  'max': (1, 8),
  'round': (1, 2),
  'abs': (1, 1),
  'eq': (2, 2),
  'gt': (2, 2),
  'gte': (2, 2),
  'lt': (2, 2),
  'lte': (2, 2),
  'and': (1, 8),
  'or': (1, 8),
  'not': (1, 1),
  'if': (3, 3),
  'floor': (1, 1),
  'ceil': (1, 1),
  'sqrt': (1, 1),
  'pow': (2, 2),
  'clamp': (3, 3),
  'percent': (2, 2),
  'change': (2, 2),
  'concat': (1, 8),
};

/// Reads old `{{key}}` text bindings as explicit `concat` expressions over declared state.
Json _legacyBindings(Json document) {
  final state = document['state'];
  if (state != null && state is! Map) return document;
  final known = asJson(state);
  Object? concat(List<Object?> initial) {
    var parts = initial;
    while (parts.length > 8) {
      parts = [
        for (var i = 0; i < parts.length; i += 8)
          {
            'op': 'concat',
            'args': parts.sublist(
              i,
              i + 8 > parts.length ? parts.length : i + 8,
            ),
          },
      ];
    }
    return {'op': 'concat', 'args': parts};
  }

  Object? walk(Object? node, int depth) {
    if (node is! Map || depth > maxVisualDepth) return node;
    final result = asJson(node).map(MapEntry.new);
    final text = node['text'];
    if ((node['type'] == 'text' || node['type'] == 'badge') &&
        !node.containsKey('value') &&
        text is String &&
        text.length <= 4000 &&
        _hasPlaceholder(text)) {
      final parts = <Object?>[];
      var position = 0;
      var valid = true;
      for (final m in RegExp(r'\{\{([^{}]+)\}\}').allMatches(text)) {
        final key = m[1];
        if (!_isKey(key) ||
            !known.containsKey(key) ||
            !isVisualScalar(known[key])) {
          valid = false;
          break;
        }
        if (m.start > position) parts.add(text.substring(position, m.start));
        parts.add({'state': key});
        position = m.end;
      }
      if (position < text.length) parts.add(text.substring(position));
      if (valid && parts.isNotEmpty && !parts.any(_hasPlaceholder)) {
        result.remove('text');
        result['value'] = concat(parts);
      }
    }
    final children = node['children'];
    if (children is List && children.length <= 40) {
      result['children'] = [for (final c in children) walk(c, depth + 1)];
    }
    return result;
  }

  return {...document, 'root': walk(document['root'], 0)};
}

bool _validValue(
  Object? value,
  Set<String> state,
  Set<String> facts, [
  int depth = 0,
]) {
  if (depth > 8) return false;
  if (isVisualScalar(value)) return !_hasPlaceholder(value);
  if (value is! Map) return false;
  if (_fieldsOnly(value, ['state']) && value['state'] is String) {
    return state.contains(value['state']);
  }
  if (_fieldsOnly(value, ['source']) && value['source'] is String) {
    return facts.contains(value['source']);
  }
  final op = value['op'];
  if (!_fieldsOnly(value, ['op', 'args']) ||
      op is! String ||
      !_operatorArity.containsKey(op) ||
      !_array(value['args'], 8)) {
    return false;
  }
  final (minimum, maximum) = _operatorArity[op]!;
  final args = value['args'] as List;
  return args.length >= minimum &&
      args.length <= maximum &&
      args.every((item) => _validValue(item, state, facts, depth + 1));
}

bool _validAction(Object? value) {
  if (value is! Map || !_fieldsOnly(value, ['kind', 'text', 'resource_id'])) {
    return false;
  }
  if (value['kind'] == 'follow_up') {
    final text = value['text'];
    return text is String &&
        text.trim().isNotEmpty &&
        text.length <= 2000 &&
        value['resource_id'] == null;
  }
  return _literal(value['kind'], ['open_chart', 'open_artifact']) &&
      value['resource_id'] is String &&
      resourcePattern.hasMatch(value['resource_id'] as String) &&
      value['text'] == null;
}

/// A validated v1 document, or null (unknown properties fail closed).
Json? validateVisualDocument(Object? input) {
  try {
    if (input is! Map) return null;
    var value = asJson(input);
    if (!_fieldsOnly(value, ['version', 'mode', 'root', 'state', 'facts']) ||
        value['version'] != 1 ||
        !_literal(value['mode'], ['observed', 'example', 'estimate'])) {
      return null;
    }
    value = _legacyBindings(value);
    final state = value['state'] ?? const {};
    final facts = value['facts'] ?? const {};
    if (state is! Map ||
        state.length > 20 ||
        !state.entries.every(
          (e) =>
              _isKey(e.key) &&
              isVisualScalar(e.value) &&
              !_hasPlaceholder(e.value),
        )) {
      return null;
    }
    if (facts is! Map ||
        facts.length > 200 ||
        !facts.entries.every((e) {
          final fact = e.value;
          return _isKey(e.key) &&
              fact is Map &&
              _fieldsOnly(fact, ['value', 'source', 'observed_at']) &&
              fact.containsKey('value') &&
              isVisualScalar(fact['value']) &&
              !_hasPlaceholder(fact['value']) &&
              _text(fact['source'], 100) &&
              (!fact.containsKey('observed_at') ||
                  _text(fact['observed_at'], 80, true));
        })) {
      return null;
    }
    final stateKeys = state.keys.cast<String>().toSet();
    final factKeys = facts.keys.cast<String>().toSet();
    final seen = <String>{};
    bool expressions(Object? item) => _validValue(item, stateKeys, factKeys);
    bool walk(Object? node, int depth) {
      if (depth > maxVisualDepth ||
          node is! Map ||
          !_isKey(node['id']) ||
          seen.contains(node['id']) ||
          seen.length >= maxVisualNodes ||
          node['type'] is! String ||
          !_allowed.containsKey(node['type'])) {
        return false;
      }
      final kind = node['type'] as String;
      if (!_fieldsOnly(node, [..._common, ..._allowed[kind]!])) return false;
      seen.add(node['id'] as String);
      for (final field in ['text', 'label']) {
        if (node.containsKey(field) &&
            !_text(node[field], field == 'text' ? 4000 : 300, true)) {
          return false;
        }
      }
      if (node.containsKey('tone') &&
          !_literal(node['tone'], [
            'neutral',
            'info',
            'success',
            'warning',
            'danger',
          ])) {
        return false;
      }
      if (node.containsKey('gap') &&
          !_literal(node['gap'], ['small', 'normal', 'large'])) {
        return false;
      }
      if (node.containsKey('level') &&
          (!_numeric(node['level'], 1, 4) || !_int(node['level']))) {
        return false;
      }
      if (node.containsKey('columns') &&
          (!_numeric(node['columns'], 1, 3) || !_int(node['columns']))) {
        return false;
      }
      if (node.containsKey('chart_kind') &&
          !_literal(node['chart_kind'], ['line', 'bar', 'pie'])) {
        return false;
      }
      if (node.containsKey('input_kind') &&
          !_literal(node['input_kind'], ['text', 'number'])) {
        return false;
      }
      for (final field in ['value', 'unit', 'visible']) {
        if (node.containsKey(field) && !expressions(node[field])) return false;
      }
      if ((kind == 'metric' || kind == 'progress') &&
          !node.containsKey('value')) {
        return false;
      }
      for (final field in ['state_key', 'filter_key']) {
        final key = node[field];
        if (key != null && (!_isKey(key) || !stateKeys.contains(key))) {
          return false;
        }
      }
      if (['select', 'checkbox', 'slider', 'input', 'tabs'].contains(kind) &&
          (node['state_key'] is! String ||
              !stateKeys.contains(node['state_key']))) {
        return false;
      }
      if (node.containsKey('minimum') && !_numeric(node['minimum'])) {
        return false;
      }
      if (node.containsKey('maximum') && !_numeric(node['maximum'])) {
        return false;
      }
      if (node.containsKey('step') &&
          (!_numeric(node['step']) || (node['step'] as num) <= 0)) {
        return false;
      }
      if (((node['maximum'] as num?) ?? 100) <
          ((node['minimum'] as num?) ?? 0)) {
        return false;
      }
      final options = node['options'];
      if (options != null) {
        if (!_array(options, 20) ||
            !(options as List).every(
              (item) =>
                  item is Map &&
                  _fieldsOnly(item, ['value', 'label']) &&
                  _text(item['value'], 100) &&
                  _text(item['label'], 160),
            )) {
          return false;
        }
        if (options.map((o) => (o as Map)['value']).toSet().length !=
            options.length) {
          return false;
        }
      }
      if ((kind == 'select' || kind == 'tabs') &&
          (options is! List || options.isEmpty)) {
        return false;
      }
      final stateKey = node['state_key'];
      final initial = stateKey is String ? state[stateKey] : null;
      if ((kind == 'select' || kind == 'tabs') &&
          !(options as List).any((o) => (o as Map)['value'] == initial)) {
        return false;
      }
      if (kind == 'checkbox' && initial is! bool) return false;
      if ((kind == 'slider' ||
              (kind == 'input' && node['input_kind'] == 'number')) &&
          !_numeric(
            initial,
            (node['minimum'] as num?) ?? 0,
            (node['maximum'] as num?) ?? 100,
          )) {
        return false;
      }
      if (kind == 'input' &&
          (node['input_kind'] ?? 'text') == 'text' &&
          initial is! String) {
        return false;
      }
      final filterKey = node['filter_key'];
      if (filterKey is String && state[filterKey] is! String) return false;
      final children = node['children'];
      if (children != null &&
          (!_array(children, 40) ||
              !(children as List).every((c) => walk(c, depth + 1)))) {
        return false;
      }
      if (kind == 'tabs' &&
          (options as List).length !=
              ((children as List?) ?? const []).length) {
        return false;
      }
      final fields = node['fields'];
      if (fields != null &&
          (!_array(fields, 12) ||
              !(fields as List).every(
                (item) =>
                    item is Map &&
                    _fieldsOnly(item, ['key', 'label']) &&
                    _isKey(item['key']) &&
                    _text(item['label'], 160),
              ))) {
        return false;
      }
      final columnKeys = {
        for (final f in (fields as List?) ?? const []) (f as Map)['key'],
      };
      if (columnKeys.length != (fields == null ? 0 : fields.length)) {
        return false;
      }
      if (kind == 'table' && columnKeys.isEmpty) return false;
      final rows = node['rows'];
      if (rows != null &&
          (!_array(rows, 100) ||
              !(rows as List).every(
                (row) =>
                    row is Map &&
                    row.entries.every(
                      (e) => columnKeys.contains(e.key) && expressions(e.value),
                    ),
              ))) {
        return false;
      }
      final points = node['points'];
      if (points != null &&
          (!_array(points, 100) ||
              !(points as List).every(
                (p) =>
                    p is Map &&
                    _fieldsOnly(p, ['label', 'value']) &&
                    p.containsKey('label') &&
                    p.containsKey('value') &&
                    expressions(p['label']) &&
                    expressions(p['value']),
              ))) {
        return false;
      }
      final vertices = node['vertices'];
      if (vertices != null &&
          (!_array(vertices, 20) ||
              !(vertices as List).every(
                (v) =>
                    v is Map &&
                    _fieldsOnly(v, ['id', 'label']) &&
                    _isKey(v['id']) &&
                    _text(v['label'], 160),
              ))) {
        return false;
      }
      final vertexIds = {
        for (final v in (vertices as List?) ?? const []) (v as Map)['id'],
      };
      if (vertexIds.length != (vertices == null ? 0 : vertices.length)) {
        return false;
      }
      final edges = node['edges'];
      if (edges != null &&
          (!_array(edges, 30) ||
              !(edges as List).every(
                (e) =>
                    e is Map &&
                    _fieldsOnly(e, ['source', 'target', 'label']) &&
                    vertexIds.contains(e['source']) &&
                    vertexIds.contains(e['target']) &&
                    (!e.containsKey('label') || _text(e['label'], 100)),
              ))) {
        return false;
      }
      final action = node['action'];
      if (action != null && !_validAction(action)) return false;
      if (action is Map &&
          action['kind'] == 'follow_up' &&
          action['text'] is String) {
        final template = (action['text'] as String).replaceAllMapped(
          RegExp(r'\{\{([^{}]+)\}\}'),
          (m) => stateKeys.contains(m[1]) && _isKey(m[1]) ? '' : '{{invalid}}',
        );
        if (RegExp(r'\{\{|\}\}').hasMatch(template)) return false;
      }
      if (kind == 'button' &&
          (node['label'] is! String ||
              (node['label'] as String).isEmpty ||
              !_validAction(action))) {
        return false;
      }
      final artifact = node['artifact_id'];
      if (artifact != null &&
          (artifact is! String || !resourcePattern.hasMatch(artifact))) {
        return false;
      }
      if (kind == 'image' && artifact == null) return false;
      return true;
    }

    if (!walk(value['root'], 0)) return null;
    final serialized = jsonEncode(value);
    return utf8.encode(serialized).length <= maxVisualBytes ? value : null;
  } catch (_) {
    return null;
  }
}

typedef VisualState = Map<String, Object?>;

/// Pure bounded expression evaluation (`evaluateVisualValue`).
Object? evaluateVisualValue(Object? value, Json document, VisualState state) {
  final declared = asJson(document['state']);
  final facts = asJson(document['facts']);
  Object? eval(Object? item, int depth) {
    if (depth > 8 || item == null) return null;
    if (isVisualScalar(item)) return item;
    if (item is! Map) return null;
    if (item.containsKey('state')) {
      final key = item['state'];
      return state.containsKey(key) ? state[key] : declared[key];
    }
    if (item.containsKey('source')) {
      return asJson(facts[item['source']])['value'];
    }
    final op = item['op'];
    final rawArgs = item['args'];
    if (op is! String || !_operatorArity.containsKey(op) || rawArgs is! List) {
      return null;
    }
    final (lo, hi) = _operatorArity[op]!;
    if (rawArgs.length < lo || rawArgs.length > hi) return null;
    if (op == 'if') {
      return _js(eval(rawArgs[0], depth + 1))
          ? eval(rawArgs[1], depth + 1)
          : eval(rawArgs[2], depth + 1);
    }
    final args = [for (final a in rawArgs) eval(a, depth + 1)];
    if (op == 'concat') {
      if (args.any((a) => a == null)) return null;
      final result = args.map(_string).join();
      return result.runes.length <= 4000 ? result : null;
    }
    if (op == 'eq') return _eq(args[0], args[1]);
    if (op == 'and') return args.every(_js);
    if (op == 'or') return args.any(_js);
    if (op == 'not') return !_js(args[0]);
    if (!args.every((a) => a is num && a.isFinite)) return null;
    final n = args.cast<num>();
    Object? result;
    switch (op) {
      case 'add':
        result = n.fold<num>(0, (t, x) => t + x);
      case 'sub':
        result = n[0] - n[1];
      case 'mul':
        result = n.fold<num>(1, (t, x) => t * x);
      case 'div':
        result = n[1] == 0 ? null : n[0] / n[1];
      case 'min':
        result = n.reduce((a, b) => a < b ? a : b);
      case 'max':
        result = n.reduce((a, b) => a > b ? a : b);
      case 'abs':
        result = n[0].abs();
      case 'floor':
        result = n[0].floorToDouble();
      case 'ceil':
        result = n[0].ceilToDouble();
      case 'sqrt':
        result = n[0] < 0 ? null : _sqrt(n[0]);
      case 'pow':
        result = _pow(n[0], n[1]);
      case 'clamp':
        result = n[1] > n[2]
            ? null
            : (n[0] < n[1] ? n[1] : (n[0] > n[2] ? n[2] : n[0]));
      case 'percent':
        result = n[1] == 0 ? null : n[0] / n[1] * 100;
      case 'change':
        result = n[1] == 0 ? null : (n[0] - n[1]) / n[1].abs() * 100;
      case 'round':
        final places = n.length > 1 ? n[1] : 0;
        if (!_int(places) || places < 0 || places > 8) return null;
        final precision = _pow(10, places);
        result =
            ((n[0] + 2.220446049250313e-16) * precision + 0.5).floorToDouble() /
            precision;
      case 'gt':
        result = n[0] > n[1];
      case 'gte':
        result = n[0] >= n[1];
      case 'lt':
        result = n[0] < n[1];
      case 'lte':
        result = n[0] <= n[1];
      default:
        return null;
    }
    return isVisualScalar(result) ? result : null;
  }

  return eval(value, 0);
}

num _pow(num a, num b) => math.pow(a, b);

num _sqrt(num x) => math.sqrt(x);

bool _js(Object? v) {
  if (v == null || v == false) return false;
  if (v is num) return v != 0 && !v.isNaN;
  if (v is String) return v.isNotEmpty;
  return true;
}

bool _eq(Object? a, Object? b) => a is num && b is num ? a == b : a == b;

String _string(Object? v) {
  if (v is num) {
    if (v == v.truncateToDouble() && v.abs() < 1e21) {
      return BigInt.from(v).toString();
    }
    return v.toString();
  }
  return '$v';
}

Object? _controlValue(Json node, Object? value, Object? fallback) {
  final type = node['type'];
  if (type == 'checkbox') {
    return value is bool ? value : (fallback is bool ? fallback : false);
  }
  if (type == 'select' || type == 'tabs') {
    final options = asJsonList(node['options']);
    if (value is String && options.any((o) => o['value'] == value)) {
      return value;
    }
    return options.any((o) => o['value'] == fallback)
        ? fallback
        : (options.isEmpty ? null : options.first['value']);
  }
  if (type == 'slider' || (type == 'input' && node['input_kind'] == 'number')) {
    if (type == 'input' && (value == null || value == '')) return null;
    final parsed = value is num
        ? value
        : value is String && value.trim().isNotEmpty
        ? (double.tryParse(value.trim()) ?? double.nan)
        : double.nan;
    final minimum = (node['minimum'] as num?) ?? 0;
    final maximum = (node['maximum'] as num?) ?? 100;
    final step = (node['step'] as num?) ?? 1;
    final number = parsed.isFinite
        ? parsed
        : (fallback is num && fallback.isFinite ? fallback : minimum);
    final bounded = number < minimum
        ? minimum
        : (number > maximum ? maximum : number);
    if (type == 'input') return bounded;
    final snapped = minimum + ((bounded - minimum) / step).round() * step;
    final clean = double.parse(snapped.toStringAsPrecision(12));
    return clean < minimum ? minimum : (clean > maximum ? maximum : clean);
  }
  if (type == 'input') {
    if (value is String) {
      return value.length > 2000 ? value.substring(0, 2000) : value;
    }
    return fallback is String ? fallback : '';
  }
  return isVisualScalar(value) ? value : fallback;
}

void _walkNodes(Json node, void Function(Json) visit) {
  visit(node);
  for (final child in asJsonList(node['children'])) {
    _walkNodes(child, visit);
  }
}

/// Restore only declared scalar keys; nothing else can add state.
VisualState initialVisualState(Json document, [Object? saved]) {
  final stored = asJson(saved);
  final result = <String, Object?>{};
  for (final MapEntry(:key, :value) in asJson(document['state']).entries) {
    if (!_isKey(key)) continue;
    final v = stored.containsKey(key) && isVisualScalar(stored[key])
        ? stored[key]
        : value;
    result[key] = v is String && v.length > 2000 ? v.substring(0, 2000) : v;
  }
  _walkNodes(asJson(document['root']), (node) {
    final key = node['state_key'];
    if (key is String && result.containsKey(key)) {
      result[key] = _controlValue(
        node,
        result[key],
        asJson(document['state'])[key],
      );
    }
  });
  return result;
}

/// Only the declared control can update its state.
VisualState updateVisualState(
  Json document,
  VisualState state,
  String nodeId,
  Object? next,
) {
  Json? declared;
  _walkNodes(asJson(document['root']), (candidate) {
    if (candidate['id'] == nodeId) declared = candidate;
  });
  final result = initialVisualState(document, state);
  final node = declared;
  if (node == null) return result;
  final filterKey = node['filter_key'];
  if (node['type'] == 'table' && filterKey is String) {
    if (result[filterKey] is String && next is String) {
      result[filterKey] = next.length > 2000 ? next.substring(0, 2000) : next;
    }
    return result;
  }
  final key = node['state_key'];
  if (key is! String ||
      !result.containsKey(key) ||
      ![
        'checkbox',
        'select',
        'tabs',
        'slider',
        'input',
      ].contains(node['type'])) {
    return result;
  }
  result[key] = _controlValue(node, next, result[key]);
  return result;
}

/// A v1 action after its `{{key}}` data placeholders are filled, or null.
Json? expandVisualAction(Object? action, Json document, VisualState state) {
  if (!_validAction(action)) return null;
  final a = asJson(action);
  if (a['kind'] != 'follow_up') {
    return {'kind': a['kind'], 'resource_id': a['resource_id']};
  }
  var invalid = false;
  final known = initialVisualState(document, state);
  final text = a['text'] as String;
  final expanded = text.replaceAllMapped(RegExp(r'\{\{([^{}]+)\}\}'), (m) {
    final key = m[1];
    if (!_isKey(key) || !known.containsKey(key)) {
      invalid = true;
      return '';
    }
    final v = known[key];
    return v == null ? '' : _string(v);
  });
  final template = text.replaceAll(RegExp(r'\{\{([^{}]+)\}\}'), '');
  if (invalid ||
      RegExp(r'\{\{|\}\}').hasMatch(template) ||
      expanded.trim().isEmpty ||
      expanded.length > 2000) {
    return null;
  }
  return {'kind': 'follow_up', 'text': expanded};
}

/// A table's rows after its own text filter.
List<Json> filterVisualRows(Json node, Json document, VisualState state) {
  final rows = asJsonList(node['rows']);
  final filterKey = node['filter_key'];
  final query = filterKey is String
      ? '${state[filterKey] ?? ''}'.trim().toLowerCase()
      : '';
  if (query.isEmpty) return rows;
  return rows
      .where(
        (row) => row.values.any(
          (v) =>
              _display(evaluateVisualValue(v, document, state))
                  .toLowerCase()
                  .contains(query),
        ),
      )
      .toList();
}

String _display(Object? v) => v == null ? '' : _string(v);

/// The artifact ids a v1 document already shows as images (attachment cards skip them).
Set<String> visualImageIds(Json document) {
  final ids = <String>{};
  _walkNodes(asJson(document['root']), (node) {
    final id = node['artifact_id'];
    if (node['type'] == 'image' && id is String) ids.add(id);
  });
  return ids;
}

/// How a scalar value reads in a v1 document (`print`).
String visualPrint(
  Object? value, {
  required String unavailable,
  required String yes,
  required String no,
}) {
  if (value == null) return unavailable;
  if (value is bool) return value ? yes : no;
  return _string(value);
}
