// Port of packages/core/src/genui/functions.ts: the v2 card functions (docs/genui.md). Values
// mirror `genui_functions.py`; formatters build display text with Lonora's own rules (Latin
// digits, en-US grouping). A bad argument returns null: "" in templates, a dash in formatters.
import 'dart:math' as math;

import 'expr.dart';

typedef GenuiFunction = Object? Function(
  FormatContext context,
  List<Object?> args,
);

const String dash = '—';
const int _maxRange = maxItems;
const int _maxList = 100;

Object? _arg(List<Object?> args, int index, [Object? fallback]) =>
    index < args.length ? args[index] : fallback;

num? _num(Object? value) => value is num && value.isFinite ? value : null;

bool _isInteger(num value) =>
    value.isFinite && value == value.truncateToDouble();

List<num>? _nums(List<Object?> values) {
  final flat = [
    for (final value in values)
      if (value is List) ...value else value,
  ];
  final numbers = flat.map(_num).toList();
  if (numbers.isEmpty || numbers.any((n) => n == null)) return null;
  return numbers.cast<num>();
}

int? _places(Object? value, [int fallback = 0]) {
  if (value == null) return fallback;
  final number = _num(value);
  if (number == null || !_isInteger(number) || number < 0 || number > 8) {
    return null;
  }
  return number.toInt();
}

num? _finite(num value) => value.isFinite ? value : null;

num? _round(Object? value, [Object? digits]) {
  final number = _num(value);
  final d = _places(digits);
  if (number == null || d == null) return null;
  final precision = math.pow(10, d);
  return _finite((number * precision + 0.5).floorToDouble() / precision);
}

GenuiFunction _unary(num Function(num) fn) => (_, args) {
  final number = _num(_arg(args, 0));
  return number == null ? null : _finite(fn(number));
};

List<num>? _series(Object? value) {
  if (value is! List || value.length > _maxList) return null;
  final numbers = value.map(_num).toList();
  return numbers.any((n) => n == null) ? null : numbers.cast<num>();
}

const Map<String, String> _currencySigns = {
  'USD': r'$',
  'EUR': '€',
  'GBP': '£',
  'JPY': '¥',
};

String? _fixed(Object? value, Object? digits) {
  final number = _num(value);
  final d = _places(digits);
  if (number == null || d == null) return null;
  return groupNumber(number, d);
}

/// Arabic plural category of a count (functions.ts `arCount`).
String arCount(num count) {
  final n = count.truncate().abs();
  if (n == 0) return 'zero';
  if (n == 1) return 'one';
  if (n == 2) return 'two';
  final rest = n % 100;
  return rest >= 3 && rest <= 10 ? 'few' : 'many';
}

const _arWeekdays = [
  'الأحد',
  'الاثنين',
  'الثلاثاء',
  'الأربعاء',
  'الخميس',
  'الجمعة',
  'السبت',
];
const _arMonths = [
  'يناير',
  'فبراير',
  'مارس',
  'أبريل',
  'مايو',
  'يونيو',
  'يوليو',
  'أغسطس',
  'سبتمبر',
  'أكتوبر',
  'نوفمبر',
  'ديسمبر',
];
const _enWeekdays = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
];
const _enMonths = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

String _isoDay(DateTime utc) =>
    '${utc.year.toString().padLeft(4, '0')}-'
    '${utc.month.toString().padLeft(2, '0')}-'
    '${utc.day.toString().padLeft(2, '0')}';

/// The owner's local date of [now]. Without a time zone (as the Expo client calls it) the
/// UTC date, as `toISOString().slice(0, 10)`.
String localDate(DateTime now, [String? timezone]) => _isoDay(now.toUtc());

String? _dayLabel(FormatContext context, Object? value) {
  if (value is! String || !RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(value)) {
    return null;
  }
  final date = DateTime.tryParse('${value}T12:00:00Z');
  if (date == null || _isoDay(date) != value) return null;
  final en = context.language == 'en';
  final today = localDate(context.now ?? DateTime.now(), context.timezone);
  final tomorrow = DateTime.parse('${today}T12:00:00Z')
      .add(const Duration(days: 1));
  final month = (en ? _enMonths : _arMonths)[date.month - 1];
  final name = value == today
      ? (en ? 'Today' : 'اليوم')
      : value == _isoDay(tomorrow)
      ? (en ? 'Tomorrow' : 'غدًا')
      : (en ? _enWeekdays : _arWeekdays)[date.weekday % 7];
  return en ? '$name $month ${date.day}' : '$name ${date.day} $month';
}

/// How many arguments each function takes (tests/fixtures/genui/arity.json; `Random` is
/// client-only).
const Map<String, (int, int?)> genuiArity = {
  'Abs': (1, 1),
  'Allocate': (2, 2),
  'Avg': (1, 1),
  'Ceil': (1, 1),
  'Change': (1, 1),
  'Clamp': (3, 3),
  'Count': (1, 2),
  'Cumulative': (1, 1),
  'DayLabel': (1, 1),
  'Default': (1, 2),
  'Fact': (0, 1),
  'Filter': (3, 3),
  'First': (1, 1),
  'Floor': (1, 1),
  'Fmt': (1, 2),
  'If': (1, 3),
  'Includes': (2, 2),
  'Join': (1, 2),
  'Last': (1, 1),
  'Len': (1, 1),
  'Max': (0, null),
  'Min': (0, null),
  'Money': (1, 2),
  'MovingAvg': (2, 2),
  'Pct': (1, 2),
  'Pick': (1, null),
  'Plural': (1, 6),
  'Pow': (2, 2),
  'Range': (2, 3),
  'Round': (1, 2),
  'Score': (2, 2),
  'Signed': (1, 2),
  'Sqrt': (1, 1),
  'Sum': (1, 1),
  'Take': (2, 2),
  'Random': (0, 4),
};

final math.Random _random = math.Random();

final Map<String, GenuiFunction> genuiFunctions = {
  'Round': (_, a) => _round(_arg(a, 0), _arg(a, 1, 0)),
  'Floor': _unary((x) => x.floorToDouble()),
  'Ceil': _unary((x) => x.ceilToDouble()),
  'Abs': _unary((x) => x.abs()),
  'Sqrt': (_, a) {
    final number = _num(_arg(a, 0));
    return number == null || number < 0 ? null : math.sqrt(number);
  },
  'Min': (_, a) {
    final numbers = _nums(a);
    return numbers?.reduce(math.min);
  },
  'Max': (_, a) {
    final numbers = _nums(a);
    return numbers?.reduce(math.max);
  },
  'Pow': (_, a) {
    final x = _num(_arg(a, 0));
    final y = _num(_arg(a, 1));
    return x == null || y == null ? null : _finite(math.pow(x, y));
  },
  'Clamp': (_, a) {
    final x = _num(_arg(a, 0));
    final lo = _num(_arg(a, 1));
    final hi = _num(_arg(a, 2));
    return x == null || lo == null || hi == null || lo > hi
        ? null
        : math.min(math.max(x, lo), hi);
  },
  'Fmt': (_, a) => _fixed(_arg(a, 0), _arg(a, 1)) ?? dash,
  'Money': (context, a) {
    final number = _num(_arg(a, 0));
    final text = _fixed(number?.abs(), _arg(a, 1));
    if (text == null || number == null) return dash;
    final code = context.currency;
    final sign = code == null ? '' : (_currencySigns[code] ?? '$code ');
    final negative =
        number < 0 && text.replaceAll(RegExp('[0.,]'), '').isNotEmpty;
    return '${negative ? '-' : ''}$sign$text';
  },
  'Pct': (_, a) {
    final text = _fixed(_arg(a, 0), _arg(a, 1));
    return text == null ? dash : '$text%';
  },
  'Signed': (_, a) {
    final number = _num(_arg(a, 0));
    final text = _fixed(number?.abs(), _arg(a, 1));
    return text == null || number == null
        ? dash
        : '${number >= 0 ? '+' : '−'}$text';
  },
  'If': (_, a) => truthy(_arg(a, 0)) ? _arg(a, 1) : _arg(a, 2),
  'Pick': (_, a) {
    final key = _arg(a, 0);
    final pairs = a.length > 1 ? a.sublist(1) : const <Object?>[];
    for (var i = 0; i + 1 < pairs.length; i += 2) {
      if (looseEqual(key, pairs[i])) return pairs[i + 1];
    }
    return pairs.length.isOdd ? pairs.last : null;
  },
  'Len': (_, a) {
    final value = _arg(a, 0);
    if (value is String) return textSize(value);
    if (value is List) return value.length;
    if (value is Map) return value.length;
    return value == null ? 0 : null;
  },
  'Count': (_, a) {
    final value = _arg(a, 0);
    final target = _arg(a, 1, true);
    final items = value is List
        ? value
        : value is Map
        ? value.values.toList()
        : null;
    if (items == null) return value == null ? 0 : null;
    return items.where((item) => looseEqual(item, target)).length;
  },
  'Sum': (_, a) {
    final value = _arg(a, 0);
    if (value is! List) return null;
    num total = 0.0;
    for (final item in value) {
      total += _num(item) ?? 0;
    }
    return total;
  },
  'Avg': (_, a) {
    final value = _arg(a, 0);
    if (value is! List || value.isEmpty) return null;
    final numbers = value.map(_num).toList();
    if (numbers.any((n) => n == null)) return null;
    return numbers.cast<num>().fold<num>(0.0, (x, y) => x + y) / numbers.length;
  },
  'Range': (_, a) {
    final start = _num(_arg(a, 0));
    final stop = _num(_arg(a, 1));
    final step = _num(_arg(a, 2, 1));
    if (start == null ||
        stop == null ||
        step == null ||
        step == 0 ||
        (stop - start) / step < 0) {
      return null;
    }
    final count = ((stop - start) / step + 1e-9).floor() + 1;
    if (count > _maxRange) return null;
    return [for (var i = 0; i < count; i++) start + i * step];
  },
  'Includes': (_, a) {
    final values = _arg(a, 0);
    final target = _arg(a, 1);
    return values is List && values.any((item) => show(item) == show(target));
  },
  'Join': (_, a) {
    final values = _arg(a, 0);
    final separator = _arg(a, 1, '، ');
    if (values is! List || separator is! String || values.length > maxItems) {
      return null;
    }
    final parts = [for (final item in values) item == null ? '' : show(item)];
    final size =
        parts.fold<int>(0, (total, part) => total + textSize(part)) +
        textSize(separator) * math.max(parts.length - 1, 0);
    return size > maxText ? null : parts.join(separator);
  },
  'Plural': (_, a) {
    final number = _num(_arg(a, 0));
    if (number == null) return null;
    final one = _arg(a, 1, '');
    final two = _arg(a, 2, '');
    final few = _arg(a, 3, '');
    final many = _arg(a, 4, '');
    final zero = _arg(a, 5, '');
    final forms = <String, Object?>{
      'zero': truthy(zero) ? zero : many,
      'one': one,
      'two': two,
      'few': few,
      'many': many,
    };
    final form = forms[arCount(number)];
    return form == null ? '' : show(form);
  },
  'Score': (_, a) {
    final answers = _arg(a, 0);
    final key = _arg(a, 1);
    if (answers is! Map || key is! List) return null;
    var score = 0;
    for (var i = 0; i < key.length; i++) {
      if (answers.containsKey('$i') && looseEqual(answers['$i'], key[i])) {
        score++;
      }
    }
    return score;
  },
  'DayLabel': (context, a) => _dayLabel(context, _arg(a, 0)),
  'Fact': (_, _) => null,
  'First': (_, a) {
    final value = _arg(a, 0);
    return value is List && value.isNotEmpty ? value.first : null;
  },
  'Last': (_, a) {
    final value = _arg(a, 0);
    return value is List && value.isNotEmpty ? value.last : null;
  },
  'Default': (_, a) {
    final value = _arg(a, 0);
    final fallback = _arg(a, 1);
    return value == null || value == '' || (value is num && !value.isFinite)
        ? fallback
        : value;
  },
  'Take': (_, a) {
    final values = _arg(a, 0);
    final n = _num(_arg(a, 1));
    if (values is! List || n == null || !_isInteger(n)) return null;
    final count = n.toInt();
    if (count >= 0) return values.take(count).toList();
    final from = math.max(0, values.length + count);
    return values.sublist(from);
  },
  'Filter': (_, a) {
    final values = _arg(a, 0);
    final key = _arg(a, 1);
    final target = _arg(a, 2);
    if (values is! List || key is! String) return null;
    return values
        .where(
          (item) =>
              item is Map &&
              looseEqual(item.containsKey(key) ? item[key] : null, target),
        )
        .toList();
  },
  'Change': (_, a) {
    final items = _series(_arg(a, 0));
    if (items == null) return null;
    if (items.isEmpty) return <num>[];
    return [
      0.0,
      for (var i = 1; i < items.length; i++) items[i] - items[i - 1],
    ];
  },
  'Cumulative': (_, a) {
    final items = _series(_arg(a, 0));
    if (items == null) return null;
    num total = 0.0;
    return [for (final item in items) total += item];
  },
  'MovingAvg': (_, a) {
    final items = _series(_arg(a, 0));
    final size = _num(_arg(a, 1));
    if (items == null || size == null || !_isInteger(size) || size < 1) {
      return null;
    }
    final window = size.toInt();
    return [
      for (var i = 0; i < items.length; i++)
        () {
          final part = items.sublist(math.max(0, i - window + 1), i + 1);
          return part.fold<num>(0.0, (x, y) => x + y) / part.length;
        }(),
    ];
  },
  'Allocate': (_, a) {
    final amount = _num(_arg(a, 0));
    final parts = _series(_arg(a, 1));
    if (amount == null ||
        parts == null ||
        parts.isEmpty ||
        parts.any((p) => p < 0)) {
      return null;
    }
    final weight = parts.fold<num>(0, (x, y) => x + y);
    if (weight <= 0) return null;
    final cents = (amount * 100 + 0.5).floor();
    final raw = [for (final part in parts) cents * part / weight];
    final floors = [for (final value in raw) value.floor()];
    var remainder = cents - floors.fold<int>(0, (x, y) => x + y);
    final order = [for (var i = 0; i < raw.length; i++) i]
      ..sort((x, y) {
        final rx = raw[x] - floors[x];
        final ry = raw[y] - floors[y];
        final c = ry.compareTo(rx);
        return c != 0 ? c : x.compareTo(y);
      });
    for (final index in order) {
      if (remainder <= 0) break;
      floors[index] += 1;
      remainder -= 1;
    }
    return [for (final value in floors) value / 100];
  },
  'Random': (_, a) {
    final lo = _num(_arg(a, 0, 0));
    final hi = _num(_arg(a, 1, 1));
    final integer = truthy(_arg(a, 2, false));
    final count = _arg(a, 3);
    if (lo == null || hi == null || lo > hi) return null;
    num draw() => integer
        ? (lo +
                  _random.nextDouble() *
                      (hi.floorToDouble() - lo.ceilToDouble() + 1))
              .floorToDouble()
        : lo + _random.nextDouble() * (hi - lo);
    if (count == null) return draw();
    final n = _num(count);
    if (n == null || !_isInteger(n) || n < 1 || n > 50) return null;
    return [for (var i = 0; i < n; i++) draw()];
  },
};
