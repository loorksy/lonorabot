// Port of packages/core/src/genui/expr.ts and limits.ts: the lonora-ui v2 expression language
// (docs/genui.md §1). Expressions are parsed into a small AST and walked; nothing is executed.
// The shared vectors (tests/fixtures/genui/expr-vectors.json) keep this equal to the TS and
// Python evaluators. Values follow JavaScript semantics: numbers are doubles, `+` joins text,
// a missing key reads null, a non-finite result reads null.
import 'functions.dart';

const int maxExpressionChars = 400;
const int maxExpressionDepth = 12;
const int _maxParseNesting = 160;

/// Output bounds (limits.ts): no text over [maxText] code points, no list over [maxItems].
const int maxText = 2000;
const int maxItems = 201;

/// One budget for a whole value however it nests.
const int maxSize = 20000;

const _blocked = {'__proto__', 'prototype', 'constructor'};

class ExpressionError implements Exception {
  const ExpressionError(this.code);
  final String code;
  @override
  String toString() => 'ExpressionError($code)';
}

/// Code points, as Python's `len` counts them.
int textSize(String text) => text.runes.length;

/// Whether a value costs more than [limit]; stops as soon as it does.
bool overBudget(Object? value, [int limit = maxSize]) {
  var total = 0;
  final stack = <Object?>[value];
  while (stack.isNotEmpty) {
    final item = stack.removeLast();
    if (item is String) {
      total += textSize(item);
    } else if (item is List) {
      if (item.length > maxItems) return true;
      total += 1;
      stack.addAll(item);
    } else if (item is Map) {
      total += 1;
      stack.addAll(item.values);
    } else {
      total += 1;
    }
    if (total > limit) return true;
  }
  return false;
}

Object? _bounded(Object? value) {
  if (value is String) {
    if (textSize(value) > maxText) {
      throw const ExpressionError('genui_expression_too_large');
    }
  } else if ((value is List || value is Map) && overBudget(value)) {
    throw const ExpressionError('genui_expression_too_large');
  }
  return value;
}

/// A parsed expression node.
sealed class ExprNode {
  const ExprNode();
}

class _Const extends ExprNode {
  const _Const(this.value);
  final Object? value;
}

class _Var extends ExprNode {
  const _Var(this.name);
  final String name;
}

class _Local extends ExprNode {
  const _Local(this.name);
  final String name;
}

class _Array extends ExprNode {
  const _Array(this.items);
  final List<ExprNode> items;
}

class _Unary extends ExprNode {
  const _Unary(this.op, this.operand);
  final String op;
  final ExprNode operand;
}

class _Ternary extends ExprNode {
  const _Ternary(this.test, this.positive, this.negative);
  final ExprNode test;
  final ExprNode positive;
  final ExprNode negative;
}

class _Get extends ExprNode {
  const _Get(this.target, this.key);
  final ExprNode target;
  final ExprNode key;
}

class _Binary extends ExprNode {
  const _Binary(this.op, this.left, this.right);
  final String op;
  final ExprNode left;
  final ExprNode right;
}

class _Call extends ExprNode {
  const _Call(this.name, this.args);
  final String name;
  final List<ExprNode> args;
}

enum _Kind { number, string, variable, function, identifier, op, end }

class _Token {
  const _Token(this.kind, this.value);
  final _Kind kind;
  final Object value;
}

final RegExp _token = RegExp(
  r'''\s*(?:(\d+(?:\.\d+)?)|'([^']*)'|"([^"]*)"|\$([A-Za-z_][A-Za-z0-9_]*)|@([A-Za-z][A-Za-z0-9]*)|([A-Za-z_][A-Za-z0-9_]*)|(&&|\|\||==|!=|<=|>=|[-+*/%<>!?:().,[\]]))''',
);

List<_Token> _tokenize(String source) {
  if (source.length > maxExpressionChars) {
    throw const ExpressionError('genui_expression_too_long');
  }
  final tokens = <_Token>[];
  var position = 0;
  while (position < source.length) {
    if (source.substring(position).trim().isEmpty) break;
    final match = _token.matchAsPrefix(source, position);
    if (match == null || match.end == position) {
      throw const ExpressionError('genui_expression_invalid');
    }
    position = match.end;
    if (match[1] != null) {
      tokens.add(_Token(_Kind.number, double.parse(match[1]!)));
    } else if (match[2] != null) {
      tokens.add(_Token(_Kind.string, match[2]!));
    } else if (match[3] != null) {
      tokens.add(_Token(_Kind.string, match[3]!));
    } else if (match[4] != null) {
      tokens.add(_Token(_Kind.variable, match[4]!));
    } else if (match[5] != null) {
      tokens.add(_Token(_Kind.function, match[5]!));
    } else if (match[6] != null) {
      tokens.add(_Token(_Kind.identifier, match[6]!));
    } else {
      tokens.add(_Token(_Kind.op, match[7]!));
    }
  }
  tokens.add(const _Token(_Kind.end, ''));
  return tokens;
}

const List<List<String>> _levels = [
  ['||'],
  ['&&'],
  ['==', '!='],
  ['<', '<=', '>', '>='],
  ['+', '-'],
  ['*', '/', '%'],
];

class _Parser {
  _Parser(this.tokens);
  final List<_Token> tokens;
  int index = 0;
  int depth = 0;

  bool _peek(String value) {
    final token = tokens[index];
    return token.kind == _Kind.op && token.value == value;
  }

  bool _take(String value) {
    if (!_peek(value)) return false;
    index += 1;
    return true;
  }

  void _expect(String value) {
    if (!_take(value)) throw const ExpressionError('genui_expression_invalid');
  }

  void _enter() {
    depth += 1;
    if (depth > _maxParseNesting) {
      throw const ExpressionError('genui_expression_too_deep');
    }
  }

  void _leave() => depth -= 1;

  ExprNode parse() {
    final node = _ternary();
    if (tokens[index].kind != _Kind.end) {
      throw const ExpressionError('genui_expression_invalid');
    }
    return node;
  }

  ExprNode _ternary() {
    _enter();
    var node = _binary(0);
    if (_take('?')) {
      final positive = _ternary();
      _expect(':');
      node = _Ternary(node, positive, _ternary());
    }
    _leave();
    return node;
  }

  ExprNode _binary(int level) {
    if (level == _levels.length) return _unary();
    _enter();
    var left = _binary(level + 1);
    for (;;) {
      final token = tokens[index];
      if (token.kind == _Kind.op && _levels[level].contains(token.value)) {
        index += 1;
        left = _Binary(token.value as String, left, _binary(level + 1));
      } else {
        break;
      }
    }
    _leave();
    return left;
  }

  ExprNode _unary() {
    for (final op in const ['!', '-']) {
      if (_take(op)) {
        _enter();
        final node = _Unary(op, _unary());
        _leave();
        return node;
      }
    }
    return _postfix();
  }

  ExprNode _postfix() {
    var node = _primary();
    for (;;) {
      if (_take('.')) {
        final token = tokens[index];
        if (token.kind != _Kind.identifier) {
          throw const ExpressionError('genui_expression_invalid');
        }
        index += 1;
        node = _Get(node, _Const(token.value));
      } else if (_take('[')) {
        _enter();
        node = _Get(node, _ternary());
        _leave();
        _expect(']');
      } else {
        return node;
      }
    }
  }

  List<ExprNode> _list(String close) {
    final items = <ExprNode>[];
    _enter();
    if (!_take(close)) {
      for (;;) {
        items.add(_ternary());
        if (_take(close)) break;
        _expect(',');
      }
    }
    _leave();
    return items;
  }

  ExprNode _primary() {
    final token = tokens[index];
    index += 1;
    switch (token.kind) {
      case _Kind.number:
      case _Kind.string:
        return _Const(token.value);
      case _Kind.variable:
        return _Var(token.value as String);
      case _Kind.function:
        _expect('(');
        return _Call(token.value as String, _list(')'));
      case _Kind.identifier:
        if (token.value == 'true') return const _Const(true);
        if (token.value == 'false') return const _Const(false);
        if (token.value == 'null') return const _Const(null);
        return _Local(token.value as String);
      case _Kind.op:
        if (token.value == '(') {
          _enter();
          final node = _ternary();
          _leave();
          _expect(')');
          return node;
        }
        if (token.value == '[') return _Array(_list(']'));
      case _Kind.end:
        break;
    }
    throw const ExpressionError('genui_expression_invalid');
  }
}

int _astDepth(ExprNode node) =>
    1 +
    switch (node) {
      _Const() || _Var() || _Local() => 0,
      _Array(:final items) => items.fold(0, (m, n) => _max(m, _astDepth(n))),
      _Unary(:final operand) => _astDepth(operand),
      _Ternary(:final test, :final positive, :final negative) => _max(
        _astDepth(test),
        _max(_astDepth(positive), _astDepth(negative)),
      ),
      _Get(:final target, :final key) => _max(
        _astDepth(target),
        _astDepth(key),
      ),
      _Binary(:final left, :final right) => _max(
        _astDepth(left),
        _astDepth(right),
      ),
      _Call(:final args) => args.fold(0, (m, n) => _max(m, _astDepth(n))),
    };

int _max(int a, int b) => a > b ? a : b;

final Map<String, ExprNode?> _cache = {};

/// Parses [source]; throws [ExpressionError] when it is not an expression.
ExprNode parseExpression(String source) {
  if (_cache.containsKey(source)) {
    final cached = _cache[source];
    if (cached == null) throw const ExpressionError('genui_expression_invalid');
    return cached;
  }
  try {
    final node = _Parser(_tokenize(source)).parse();
    if (_astDepth(node) > maxExpressionDepth) {
      throw const ExpressionError('genui_expression_too_deep');
    }
    if (_cache.length < 4096) _cache[source] = node;
    return node;
  } catch (_) {
    if (_cache.length < 4096) _cache[source] = null;
    rethrow;
  }
}

/// Whether [source] parses (a non-string is a literal and always valid).
bool isExpression(Object? source) {
  if (source is! String) return true;
  try {
    parseExpression(source);
    return true;
  } on ExpressionError {
    return false;
  }
}

// --- values ---------------------------------------------------------------------------------

bool isNumber(Object? value) => value is num;

/// JavaScript `Number(value)` for card values.
double toNumber(Object? value) {
  if (value == null) return 0;
  if (value is bool) return value ? 1 : 0;
  if (value is num) return value.toDouble();
  if (value is String) {
    final text = value.trim();
    if (text.isEmpty) return 0;
    return RegExp(r'^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$').hasMatch(text)
        ? double.parse(text)
        : double.nan;
  }
  return double.nan;
}

/// JavaScript truthiness.
bool truthy(Object? value) {
  if (value == null || value == false) return false;
  if (value is num) return value != 0 && !value.isNaN;
  if (value is String) return value.isNotEmpty;
  return true;
}

/// JavaScript `String(number)`: integral values without «.0».
String jsNumber(num value) {
  if (value is int) return value.toString();
  if (value.isNaN) return 'NaN';
  if (value.isInfinite) return value > 0 ? 'Infinity' : '-Infinity';
  if (value == value.truncateToDouble() && value.abs() < 1e21) {
    return BigInt.from(value).toString();
  }
  return value.toString();
}

/// `show`: how a value reads inside text joined with `+`.
String show(Object? value) {
  if (value == null) return 'null';
  if (value is List) {
    return value.map((item) => item == null ? '' : show(item)).join(',');
  }
  if (value is Map) return '[object Object]';
  if (value is num) return jsNumber(value);
  return value.toString();
}

/// JavaScript loose equality for card values.
bool looseEqual(Object? left, Object? right) {
  if (left == null || right == null) return left == null && right == null;
  if (left is List || left is Map || right is List || right is Map) {
    return identical(left, right);
  }
  if (left is String && right is String) return left == right;
  if (left is bool && right is bool) return left == right;
  final a = toNumber(left);
  final b = toNumber(right);
  return !a.isNaN && !b.isNaN && a == b;
}

/// Non-finite numbers are null; everything else is as computed.
Object? normal(Object? value) {
  if (value is num && !value.isFinite) return null;
  return value;
}

bool _compare(String op, Object? left, Object? right) {
  int c;
  if (left is String && right is String) {
    c = left.compareTo(right);
  } else {
    final a = toNumber(left);
    final b = toNumber(right);
    if (a.isNaN || b.isNaN) return false;
    c = a.compareTo(b);
  }
  return switch (op) {
    '<' => c < 0,
    '<=' => c <= 0,
    '>' => c > 0,
    _ => c >= 0,
  };
}

Object? _binaryOp(String op, Object? left, Object? right) {
  if (op == '+') {
    if (left is String || right is String) {
      return _bounded(show(left) + show(right));
    }
    return toNumber(truthy(left) ? left : 0) +
        toNumber(truthy(right) ? right : 0);
  }
  if (op == '-' || op == '*' || op == '/' || op == '%') {
    final a = toNumber(left);
    final b = toNumber(right);
    if (op == '-') return a - b;
    if (op == '*') return a * b;
    if (b == 0 || b.isNaN) return 0.0;
    return op == '/' ? a / b : a.remainder(b);
  }
  if (op == '==') return looseEqual(left, right);
  if (op == '!=') return !looseEqual(left, right);
  return _compare(op, left, right);
}

/// Formatting context of a card's functions.
class FormatContext {
  const FormatContext({
    this.currency,
    this.timezone,
    this.language = 'ar',
    this.now,
    this.allowRandom = false,
  });
  final String? currency;
  final String? timezone;

  /// `ar` or `en`.
  final String language;
  final DateTime? now;

  /// Only a `set` action value may draw.
  final bool allowRandom;

  FormatContext withRandom() => FormatContext(
    currency: currency,
    timezone: timezone,
    language: language,
    now: now,
    allowRandom: true,
  );
}

/// What an expression reads: `$state` (and calcs), local names, facts.
class Env {
  Env({
    required this.values,
    required this.facts,
    Map<String, Object?>? names,
    this.context = const FormatContext(),
  }) : names = names ?? {};
  final Map<String, Object?> values;
  final Map<String, Object?> facts;
  final Map<String, Object?> names;
  final FormatContext context;

  Env withContext(FormatContext value) =>
      Env(values: values, facts: facts, names: names, context: value);
}

Object? _ownGet(Map record, String key) =>
    record.containsKey(key) ? record[key] : null;

Object? _get(Object? container, Object? key) {
  if (key is String && _blocked.contains(key)) {
    throw const ExpressionError('genui_expression_blocked');
  }
  if (container is Map) {
    return _ownGet(container, key is String ? key : show(key));
  }
  int? index(Object? key) {
    if (key is num) {
      return key == key.truncateToDouble() && key.isFinite ? key.toInt() : null;
    }
    if (key is String && RegExp(r'^\d+$').hasMatch(key)) return int.parse(key);
    return null;
  }

  if (container is String) {
    final points = container.runes.toList();
    if (key == 'length') return points.length;
    final at = index(key);
    return at != null && at >= 0 && at < points.length
        ? String.fromCharCode(points[at])
        : null;
  }
  if (container is List) {
    if (key == 'length') return container.length;
    final at = index(key);
    if (at != null && at >= 0 && at < container.length) return container[at];
  }
  return null;
}

Object? evaluateNode(ExprNode node, Env env) {
  switch (node) {
    case _Const(:final value):
      return value;
    case _Var(:final name):
      if (_blocked.contains(name)) {
        throw const ExpressionError('genui_expression_blocked');
      }
      return _bounded(_ownGet(env.values, name));
    case _Local(:final name):
      if (_blocked.contains(name)) {
        throw const ExpressionError('genui_expression_blocked');
      }
      return _bounded(_ownGet(env.names, name));
    case _Array(:final items):
      return _bounded([for (final item in items) evaluateNode(item, env)]);
    case _Unary(:final op, :final operand):
      final value = evaluateNode(operand, env);
      return op == '!' ? !truthy(value) : -toNumber(value);
    case _Ternary(:final test, :final positive, :final negative):
      return evaluateNode(
        truthy(evaluateNode(test, env)) ? positive : negative,
        env,
      );
    case _Get(:final target, :final key):
      return _bounded(_get(evaluateNode(target, env), evaluateNode(key, env)));
    case _Binary(:final op, :final left, :final right):
      final l = evaluateNode(left, env);
      if (op == '&&') return truthy(l) ? evaluateNode(right, env) : l;
      if (op == '||') return truthy(l) ? l : evaluateNode(right, env);
      return _binaryOp(op, l, evaluateNode(right, env));
    case _Call(:final name, :final args):
      final fn = genuiFunctions[name];
      if (fn == null) throw const ExpressionError('genui_function_unknown');
      if (name == 'Fact') {
        final key = args.isNotEmpty ? evaluateNode(args[0], env) : null;
        return key is String ? _ownGet(env.facts, key) : null;
      }
      if (name == 'Random' && !env.context.allowRandom) {
        throw const ExpressionError('genui_random_outside_set');
      }
      final arity = genuiArity[name] ?? (0, null);
      if (args.length < arity.$1 ||
          (arity.$2 != null && args.length > arity.$2!)) {
        throw const ExpressionError('genui_function_arity');
      }
      return _bounded(
        fn(env.context, [for (final arg in args) evaluateNode(arg, env)]),
      );
  }
}

/// `uxExpr`: non-strings are literals; a failure or non-finite result is [fallback].
Object? evaluate(Object? source, Env env, [Object? fallback]) {
  if (source is! String) return source;
  Object? value;
  try {
    value = normal(_bounded(evaluateNode(parseExpression(source), env)));
  } catch (_) {
    return fallback;
  }
  return value == null && fallback != null ? fallback : value;
}

final RegExp _template = RegExp(r'\{([^{}]*)\}');

/// `uxShow`: numbers with en-US grouping, integers without decimals, else at most 2.
String display(Object? value) {
  if (value == null) return '';
  if (value is num) {
    if (!value.isFinite) return '';
    final integral = value == value.truncateToDouble();
    return groupNumber(value, integral ? 0 : 2, trim: true);
  }
  if (value is List) return value.map(display).join('، ');
  if (value is bool) return value.toString();
  if (value is String) return value;
  return '';
}

/// Latin digits, en-US grouping; [trim] drops trailing zeros (uxShow), else fixed.
String groupNumber(num value, int digits, {bool trim = false}) {
  final negative = value < 0;
  final factor = _pow10(digits);
  final rounded = (value.abs() * factor + 0.5).floorToDouble() / factor;
  final fixed = rounded.toStringAsFixed(digits).split('.');
  var whole = fixed[0];
  var fraction = fixed.length > 1 ? fixed[1] : '';
  whole = whole.replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
  if (trim) fraction = fraction.replaceFirst(RegExp(r'0+$'), '');
  return '${negative && rounded != 0 ? '-' : ''}$whole'
      '${fraction.isEmpty ? '' : '.$fraction'}';
}

double _pow10(int digits) {
  var f = 1.0;
  for (var i = 0; i < digits; i++) {
    f *= 10;
  }
  return f;
}

/// Fills a card text's `{expr}` pieces.
String renderTemplate(String text, Env env) =>
    text.replaceAllMapped(_template, (match) {
      final shown = display(evaluate(match[1], env, ''));
      return textSize(shown) > maxText ? '' : shown;
    });

/// `values` over `state`, then each calc in order into the same `$` namespace.
Env environment(
  Map<String, Object?> state,
  Map<String, Object?> calc,
  Map<String, Object?> facts, {
  Map<String, Object?>? values,
  FormatContext context = const FormatContext(),
}) {
  final current = <String, Object?>{...state, ...?values};
  final env = Env(values: current, facts: facts, context: context);
  for (final MapEntry(:key, :value) in calc.entries) {
    current[key] = evaluate(value, env);
  }
  return env;
}
