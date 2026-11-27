import '../../../l10n/l10n.dart';

/// Android-only labels of the usage pages, in the Web's wording (apps/web UsagePage.tsx and
/// its ar catalog). «All time» heads the server's lifetime token totals (Android). A percent
/// is passed with its sign inside the value, so it stays with its number in Arabic.
void registerUsageStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('us_title')) return;
  target.register(_usageStrings);
}

const Map<String, List<String>> _usageStrings = {
  'us_title': ['الاستهلاك العام', 'Overall usage'],
  'us_detailTitle': ['تفاصيل الاستهلاك', 'Usage details'],
  'us_period': ['الفترة', 'Period'],
  'us_7days': ['7 أيام', '7 days'],
  'us_30days': ['30 يومًا', '30 days'],
  'us_todaySoFar': ['اليوم حتى الآن', 'today so far'],
  'us_last7': ['آخر 7 أيام', 'the last 7 days'],
  'us_last30': ['آخر 30 يومًا', 'the last 30 days'],
  'us_sameTimeYesterday': ['نفس الوقت أمس', 'the same time yesterday'],
  'us_prev7': ['الأيام السبعة السابقة', 'the previous seven days'],
  'us_prev30': ['الثلاثين يومًا السابقة', 'the previous thirty days'],
  'us_costWindow': ['التكلفة · {0}', 'Cost · {0}'],
  'us_comparedWith': ['مقارنة ب{0} · {1}', 'Compared with {0} · {1}'],
  'us_noChange': ['دون تغيير', 'No change'],
  'us_up': ['ارتفاع {0}', 'Up {0}'],
  'us_down': ['انخفاض {0}', 'Down {0}'],
  'us_monthSoFar': ['{0} حتى الآن', '{0} so far'],
  'us_projected': ['المتوقع {0}', 'projected {0}'],
  'us_dayOf': ['اليوم {0} من {1}', 'Day {0} of {1}'],
  'us_projectedTo': ['المتوقع حتى {0} {1}', 'Projected to {0} {1}'],
  'us_noCap': [
    'دون سقف للإنفاق: لا يوقف الاستهلاك أي طلب.',
    'No spending cap: usage never stops a request.',
  ],
  'us_now': ['الآن', 'now'],
  'us_hour': ['الساعة', 'Hour'],
  'us_day': ['اليوم', 'Day'],
  'us_cost': ['التكلفة', 'Cost'],
  'us_tokens': ['التوكن', 'Tokens'],
  'us_showTable': ['عرض كجدول', 'Show as a table'],
  'us_showChart': ['عرض كرسم', 'Show as a chart'],
  'us_costPerHour': ['التكلفة لكل ساعة اليوم', 'Cost per hour today'],
  'us_dailyCost': ['التكلفة اليومية', 'Daily cost'],
  'us_inputOutput': ['إدخال {0} · إخراج {1}', 'Input {0} · output {1}'],
  'us_requests': ['الطلبات', 'Requests'],
  'us_perRequest': ['نحو {0} توكن للطلب', 'About {0} tokens per request'],
  'us_fromCache': ['من الذاكرة المؤقتة', 'From the cache'],
  'us_tokensReused': ['{0} توكن أُعيد استخدامها', '{0} tokens reused'],
  'us_avgCost': ['متوسط تكلفة الطلب', 'Average cost per request'],
  // A count in the language's own plural (one, two, 3–10, 11 and more).
  'us_unpriced1': ['طلب واحد دون سعر معلن', 'One request has no list price'],
  'us_unpriced2': ['طلبان دون سعر معلن', '2 requests have no list price'],
  'us_unpricedFew': [
    '{0} طلبات دون سعر معلن',
    '{0} requests have no list price',
  ],
  'us_unpricedMany': [
    '{0} طلبًا دون سعر معلن',
    '{0} requests have no list price',
  ],
  'us_perCompleted': ['لكل طلب مكتمل', 'Per completed request'],
  'us_byAgent': ['حسب الوكيل', 'By agent'],
  'us_ofTotal': ['من إجمالي التكلفة', 'of the total cost'],
  'us_byModel': ['حسب النموذج', 'By model'],
  'us_noUsage': ['لا استهلاك في هذه الفترة.', 'No usage in this period.'],
  'us_breakdown': ['توزيع الاستهلاك', 'Usage breakdown'],
  'us_shareOfTotal': ['{0} من الإجمالي', '{0} of the total'],
  'us_exportCsv': ['تصدير CSV', 'Export CSV'],
  'us_allTime': ['منذ البداية', 'All time'],
};
