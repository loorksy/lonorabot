/// Port of packages/core/src/trading-readiness.ts: the agent's trading status line, its
/// sheet's labels and the short local time they show. [isolate] and [listSeparator] live in
/// ../bidi.dart.
library;

import '../bidi.dart';
import '../format.dart';
import 'core_tables.g.dart';
import 'text.dart';
import 'values.dart';

export '../bidi.dart' show isolate, listSeparator;

/// The trading-safety sheet's labels in [locale]'s language (trading-readiness.ts:73-75).
TradingSafetyText tradingSafetyText(String locale) =>
    tradingSafetyLabels[language(locale)]!;

/// A short local time today, otherwise day and time; isolated for Arabic text
/// (trading-readiness.ts:77-88: `toLocaleString(language, {hour, minute: "2-digit"})`, with
/// `day: "numeric", month: "short"` on another day).
String readinessTime(Object iso, String locale, DateTime now) {
  final when = parseDate(iso);
  if (when == null) return isolate('Invalid Date');
  final local = now.toLocal();
  final sameDay =
      when.year == local.year &&
      when.month == local.month &&
      when.day == local.day;
  final lang = language(locale);
  final pattern = sameDay
      ? 'hh:mm a'
      : lang == 'ar'
      ? 'd MMM، hh:mm a'
      : 'MMM d, hh:mm a';
  return isolate(formatDate(pattern, lang, when));
}

/// The one line: whether the agent trades on its own or asks first, or the strongest thing
/// stopping it. [readiness] is the server's TradingReadiness JSON; [accountName] names the
/// grant's account when the owner has several (trading-readiness.ts:90-150).
String tradingReadinessLine(
  Map<String, Object?> readiness,
  String locale,
  DateTime now, [
  String? Function(String id)? accountName,
]) {
  final lang = language(locale);
  final ar = lang == 'ar';
  final params = obj(readiness['params']);
  String until(Object? iso, String openEn, String openAr) => truthy(iso)
      ? '${ar ? 'حتى' : 'until'} ${readinessTime(iso!, locale, now)}'
      : ar
      ? openAr
      : openEn;
  switch (readiness['state']) {
    case 'no_trading':
      return ar
          ? 'لا يتداول$dotSeparatorتحليل فقط'
          : 'No trading${dotSeparator}analysis only';
    case 'agent_paused':
      return ar
          ? 'الوكيل متوقف مؤقتًا$dotSeparatorلا صفقات جديدة'
          : 'Agent paused${dotSeparator}no new trades';
    case 'uncertain':
      final count = number(params['count']) ?? 1;
      final head = ar
          ? count == 1
                ? 'عملية بانتظار تأكيد الوسيط'
                : 'عمليات بانتظار تأكيد الوسيط: ${isolate(jsString(count))}'
          : count == 1
          ? '1 operation awaiting broker confirmation'
          : '${jsString(count)} operations awaiting broker confirmation';
      final symbol = str(params['symbol']);
      final held = symbol != null && symbol.isNotEmpty
          ? ar
                ? '$dotSeparatorالمخاطرة الجديدة على ${isolate(symbol)} معلّقة'
                : '${dotSeparator}new risk on $symbol held'
          : '';
      return head + held;
    case 'ask_me':
      return ar ? 'يسألك قبل كل صفقة' : 'Asks you before each trade';
    case 'on_its_own':
      // Full: every account and market, until the mode changes; no grant terms apply.
      if (readiness['trading_mode'] == 'full') {
        return ar ? 'يتداول باستقلال' : 'Trades on its own';
      }
      final accounts = number(params['account_count']) ?? 1;
      if (accounts > 1) {
        return ar
            ? 'يتداول باستقلال على ${isolate(jsString(accounts))} حسابات'
            : 'Trades on its own on ${jsString(accounts)} accounts';
      }
      final accountId = str(params['account_id']);
      final account = truthy(accountId) ? accountName?.call(accountId!) : null;
      final text = tradingSafetyLabels[lang]!;
      final markets = truthy(params['full_delegation'])
          ? text.fullDelegation
          : params['symbol_scope'] == 'account'
          ? text.allPairs
          : strings(params['symbols']).map(isolate).join(listSeparator(locale));
      final end = until(
        params['valid_until'],
        'until you stop it',
        'حتى توقفه',
      );
      final named = account != null && account.isNotEmpty
          ? '$dotSeparator${isolate(account)}'
          : '';
      final scope = markets.isNotEmpty ? '$dotSeparator$markets' : '';
      return '${ar ? 'يتداول باستقلال' : 'Trades on its own'}$named$scope$dotSeparator$end';
  }
  return '';
}

/// The pill's tone: ready, asks, held or idle (trading-readiness.ts:152-166).
String tradingReadinessTone(Map<String, Object?> readiness) =>
    switch (readiness['state']) {
      'on_its_own' => 'ready',
      'ask_me' => 'asks',
      'no_trading' => 'idle',
      _ => 'held',
    };
