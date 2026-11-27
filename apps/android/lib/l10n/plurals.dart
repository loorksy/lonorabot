/// The Expo app's hand-written count phrases, with its Arabic counts (one, two, 3–10, 11 and more).
/// [locale] is the app locale, `ar` or `en`, as in the TS.
library;

/// «محادثة واحدة» / "one chat" (apps/mobile/lib/i18n.ts:997-1004 `chatsWord`). English
/// writes 2 in digits like every other count (Arabic keeps its dual).
String chatsWord(String locale, int count) {
  if (locale == 'en') return count == 1 ? 'one chat' : '$count chats';
  if (count == 1) return 'محادثة واحدة';
  if (count == 2) return 'محادثتان';
  return count <= 10 ? '$count محادثات' : '$count محادثة';
}

/// The toast after the offline queue went out by itself (Q6), with Web's Arabic plural forms
/// (apps/mobile/lib/i18n.ts:1005-1016 `waitingSentText`).
String waitingSentText(String locale, int count) {
  if (locale == 'en') {
    return count == 1
        ? 'One waiting message was sent'
        : count == 2
        ? 'Two waiting messages were sent'
        : '$count waiting messages were sent';
  }
  if (count == 1) return 'أُرسلت رسالة واحدة كانت تنتظر';
  if (count == 2) return 'أُرسلت رسالتان كانت تنتظر';
  return count <= 10
      ? 'أُرسلت $count رسائل كانت تنتظر'
      : 'أُرسلت $count رسالة كانت تنتظر';
}

/// «وكيل واحد» / "one agent"; Arabic also has 11–99 «وكيلًا» and 100+ «وكيل»
/// (apps/mobile/lib/i18n.ts:1017-1023 `agentsWord`). English writes 2 in digits like every
/// other count (Arabic keeps its dual).
String agentsWord(String locale, int count) {
  if (locale == 'en') return count == 1 ? 'one agent' : '$count agents';
  if (count == 1) return 'وكيل واحد';
  if (count == 2) return 'وكيلان';
  return count <= 10
      ? '$count وكلاء'
      : count <= 99
      ? '$count وكيلًا'
      : '$count وكيل';
}

/// The offline strip's queued count, '' when nothing waits
/// (apps/mobile/components/shell/network-strip.tsx:33-46).
String networkWaitingText(String locale, int queued) {
  if (queued <= 0) return '';
  if (locale == 'ar') {
    return queued == 1
        ? 'رسالة واحدة تنتظر'
        : queued == 2
        ? 'رسالتان تنتظران'
        : queued <= 10
        ? '$queued رسائل تنتظر'
        : '$queued رسالة تنتظر';
  }
  return queued == 1 ? 'one message waiting' : '$queued messages waiting';
}

/// The Arabic plural category of a count: zero, one, two, few (3–10 of each hundred), many
/// (packages/core/src/genui/functions.ts:58-66 `arCount`).
String arCount(num count) {
  final n = count.truncate().abs();
  if (n == 0) return 'zero';
  if (n == 1) return 'one';
  if (n == 2) return 'two';
  final rest = n % 100;
  return rest >= 3 && rest <= 10 ? 'few' : 'many';
}

/// The form of [count] by [arCount]; zero falls back to [many] when it is empty
/// (packages/core/src/genui/functions.ts:283-290 `Plural`).
String plural(
  num count, {
  String one = '',
  String two = '',
  String few = '',
  String many = '',
  String zero = '',
}) => switch (arCount(count)) {
  'zero' => zero.isNotEmpty ? zero : many,
  'one' => one,
  'two' => two,
  'few' => few,
  _ => many,
};
