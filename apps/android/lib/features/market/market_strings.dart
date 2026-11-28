import '../../l10n/l10n.dart';
import '../trading/trading_strings.dart';

/// Android-only labels of the Market tab. Where the Web already words the same thing (apps/web
/// pages/Market.tsx, components/market/*, shell/agent/TradesPage.tsx and its ar catalog), its
/// wording is reused; Lonora's existing keys (bid, ask, quote, symbol, timeframe, simulation,
/// brokerAccount, chooseBrokerAccount, searchBrokerSymbols…) are used directly.
/// The owner's order labels (lib/features/trading) come with them: the Market tab offers its
/// orders.
void registerMarketStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  registerTradingStrings(target);
  if (target.has('mk_positions')) return;
  target.register(_marketStrings);
}

const Map<String, List<String>> _marketStrings = {
  'mk_positions': ['الصفقات', 'Positions'],
  'mk_pendingOrders': ['الأوامر المعلقة', 'Pending orders'],
  'mk_orderLog': ['سجل الأوامر', 'Order log'],
  'mk_balance': ['الرصيد', 'Balance'],
  'mk_equity': ['حقوق الملكية', 'Equity'],
  'mk_margin': ['الهامش', 'Margin'],
  'mk_freeMargin': ['الهامش المتاح', 'Free margin'],
  'mk_profit': ['الربح', 'Profit'],
  'mk_openPrice': ['سعر الفتح', 'Open price'],
  'mk_buy': ['شراء', 'Buy'],
  'mk_sell': ['بيع', 'Sell'],
  'mk_spread': ['فارق السعر', 'Spread'],
  'mk_source': ['المصدر', 'Source'],
  'mk_instrument': ['الأداة المالية', 'Instrument'],
  'mk_tickSize': ['أصغر حركة سعرية', 'Tick size'],
  'mk_volumeMin': ['أدنى حجم', 'Minimum volume'],
  'mk_volumeStep': ['خطوة الحجم', 'Volume step'],
  'mk_volumeMax': ['أقصى حجم', 'Maximum volume'],
  'mk_calendar': ['التقويم الاقتصادي', 'Economic calendar'],
  'mk_calendarEmpty': [
    'أضف مصدرًا للتقويم الاقتصادي في التكاملات لتحميل الأحداث.',
    'Add an economic calendar feed in Integrations to load events.',
  ],
  'mk_watches': ['المراقبات', 'Watches'],
  'mk_simulationNote': [
    'محاكاة · بيانات مستوردة',
    'Simulation · imported snapshot',
  ],
  'mk_linkAccount': [
    'اربط حساب تداول أولًا من الإعدادات.',
    'Link a trading account from Settings first.',
  ],
  'mk_noPositions': ['لا توجد صفقات مفتوحة.', 'No open positions.'],
  'mk_noSymbols': [
    'لا توجد أسواق متابَعة بعد. ابحث عن رمز لعرض سعره.',
    'No markets followed yet. Search a symbol to see its price.',
  ],
  'mk_opportunities': ['الفرص', 'Opportunities'],
  'mk_opp_forming': ['قيد التكوّن', 'Forming'],
  'mk_opp_confirmed': ['مؤكدة', 'Confirmed'],
  'mk_opp_degraded': ['ضعفت', 'Weakened'],
  'mk_opp_invalidated': ['لم تعد صالحة', 'Invalidated'],
  'mk_opp_expired': ['انتهت', 'Expired'],
  'mk_opp_acted_on': ['جرى التصرف بها', 'Acted on'],
  'mk_opp_completed': ['اكتملت', 'Completed'],
  'mk_openChart': ['فتح الرسم البياني', 'Open chart'],
  'mk_cancelWatch': ['إلغاء المراقبة', 'Cancel watch'],
  'mk_cancelWatchQ': ['إلغاء هذه المراقبة؟', 'Cancel this watch?'],
  'mk_cancelWatchBody': [
    'تتوقف المراقبة نهائيًا ولا يُنبَّه الوكيل عند تحقق شرطها.',
    'The watch stops for good and its agent is not woken when the condition is met.',
  ],
  'mk_watchCancelled': ['أُلغيت المراقبة', 'Watch cancelled'],
  'mk_watchPaused': ['أُوقفت المراقبة مؤقتًا', 'The watch is paused'],
  'mk_watchResumed': ['استُؤنفت المراقبة', 'The watch resumed'],
  'mk_extendWatch': ['تمديد ساعتين', 'Extend two hours'],
  'mk_watchExtended': ['مُدّدت ساعتين', 'Extended by two hours'],
  'mk_disabled': ['معطّل', 'Disabled'],
  'mk_keep': ['إبقاء', 'Keep'],
  'mk_dayChange': ['تغيّر اليوم', 'Day change'],
  'mk_accountMenu': ['تغيير الحساب', 'Change account'],
  'mk_createWatch': ['إنشاء مراقبة', 'Create watch'],
  'mk_watchCreated': ['أُنشئت المراقبة', 'Watch created'],
  'mk_condition': ['الشرط', 'Condition'],
  'mk_crossAbove': ['يتجاوز إلى الأعلى', 'Crosses above'],
  'mk_crossBelow': ['يتجاوز إلى الأسفل', 'Crosses below'],
  'mk_above': ['أعلى من', 'Above'],
  'mk_below': ['أقل من', 'Below'],
  'mk_priceLevel': ['المستوى السعري', 'Price level'],
  'mk_watchTask': ['المهمة عند تحقق الشرط', 'Task when triggered'],
  'mk_agent': ['الوكيل', 'Agent'],
  'mk_watchSource': ['مصدر المراقبة', 'Watch source'],
  'mk_srcPrice': ['السعر', 'Price'],
  'mk_srcIndicator': ['المؤشر', 'Indicator'],
  'mk_srcPosition': ['الصفقة', 'Position'],
  'mk_srcAccount': ['تغيرات الحساب', 'Account changes'],
  'mk_indicator': ['المؤشر', 'Indicator'],
  'mk_period': ['الفترة', 'Period'],
  'mk_positionId': ['معرّف الصفقة', 'Position ID'],
  'mk_metric': ['المقياس', 'Metric'],
  'mk_calendarFeed': ['مصدر التقويم الاقتصادي', 'Economic calendar feed'],
  'mk_due': ['حان موعد الحدث', 'Event is due'],
  'mk_changed': ['يتغيّر', 'Changes'],
  'mk_closed': ['يُغلق', 'Closes'],
  'mk_opened': ['يُفتح', 'Opens'],
  'mk_level': ['المستوى', 'Level'],
  'mk_watchNote': [
    'المراقبة توقظ الوكيل بالمهمة عند تحقق الشرط، ولا تمنحه أي صلاحية تداول.',
    'The watch wakes the agent with the task when the condition is met; it grants no trading authority.',
  ],
};
