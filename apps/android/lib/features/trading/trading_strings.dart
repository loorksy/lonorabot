import 'package:flutter/widgets.dart';

import '../../l10n/l10n.dart';

/// Labels of the owner's orders («الصفقات», the order ticket and its review) and of
/// «التعطل والاستعادة». Where the Web words the same thing (apps/web shell/agent/TradesPage.tsx,
/// RecoveryPage.tsx, components/trading/*, lib/user_error.ts and its ar catalog) its words are
/// used; Lonora's existing keys (stopLoss, takeProfit, orderPrice, receiptVolume, approvalAtMarket,
/// sh_cancel, save, account, mk_buy, mk_sell, mk_orderLog, mk_pendingOrders…) are used directly.
/// Error texts are keyed by the server's code, so `errorText` finds them.
void registerTradingStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('tr_title')) return;
  target.register(_tradingStrings);
}

/// [registerTradingStrings] for the catalog of [context].
void ensureTradingStrings(BuildContext context) =>
    registerTradingStrings(context.l10n);

const Map<String, List<String>> _tradingStrings = {
  // «الصفقات» (TradesPage.tsx).
  'tr_title': ['الصفقات', 'Trades'],
  'tr_noAccountChosen': [
    'لم يُختر حساب تداول لهذا الوكيل.',
    'No trading account was chosen for this agent.',
  ],
  'tr_noOpenTrade': ['لا توجد صفقة مفتوحة.', 'No open trade.'],
  'tr_noOrders': ['لا أوامر بعد.', 'No orders yet.'],
  'tr_noPendingOrders': ['لا توجد أوامر معلقة', 'No pending orders'],
  'tr_filledNote': [
    'لا تظهر حالة «منفَّذ» إلا بدليل من الوسيط أو بتأكيدك.',
    '«Filled» shows only with the broker\'s evidence or your confirmation.',
  ],
  'tr_entryPrice': ['سعر الدخول', 'Entry price'],
  'tr_editStopTarget': ['تعديل الوقف والهدف', 'Edit stop and target'],
  'tr_closeTrade': ['إغلاق الصفقة', 'Close the trade'],
  'tr_closeBody': [
    'تُغلق الصفقة على {0} بسعر السوق. هذا أمرك أنت، يُرسَل عبر المنفّذ.',
    'The trade on {0} is closed at the market price. This is your own order, sent through the executor.',
  ],
  'tr_checkCloseResult': ['تحقق من نتيجة الإغلاق', 'Check close result'],
  'tr_cancelOrder': ['إلغاء الأمر', 'Cancel order'],
  'tr_checkCancelResult': ['تحقق من نتيجة الإلغاء', 'Check cancel result'],
  'tr_editOrder': ['تعديل الأمر', 'Edit order'],
  // Order states (order-state.ts, msgctxt "order state").
  'tr_st_requested': ['مطلوب', 'Requested'],
  'tr_st_sent': ['مُرسَل', 'Sent'],
  'tr_st_accepted': ['مقبول لدى الوسيط', 'Accepted by the broker'],
  'tr_st_partial': ['منفَّذ جزئيًا', 'Partly filled'],
  'tr_st_filled': ['منفَّذ', 'Filled'],
  'tr_st_rejected': ['مرفوض', 'Rejected'],
  'tr_st_cancelled': ['ملغى', 'Cancelled'],
  'tr_st_uncertain': ['غير مؤكَّد', 'Unconfirmed'],
  // Kinds of order (TradesPage.tsx `orderWording`).
  'tr_limitOrder': ['أمر محدد', 'Limit order'],
  'tr_stopOrder': ['أمر إيقاف', 'Stop order'],
  'tr_protectionChange': ['تعديل الحماية', 'Protection change'],
  'tr_pendingOrder': ['أمر معلّق', 'Pending order'],
  // The order ticket (TradeActionCard.tsx).
  'tr_tradeAction': ['عملية تداول', 'Trade action'],
  'tr_exactSymbol': ['رمز الوسيط كما هو', 'Exact broker symbol'],
  'tr_chooseInstrument': ['اختر أداة مالية', 'Choose an instrument'],
  'tr_action': ['الإجراء', 'Action'],
  'tr_marketBuy': ['شراء بسعر السوق', 'Market buy'],
  'tr_marketSell': ['بيع بسعر السوق', 'Market sell'],
  'tr_buyLimit': ['شراء بحد سعري', 'Buy limit'],
  'tr_sellLimit': ['بيع بحد سعري', 'Sell limit'],
  'tr_buyStop': ['شراء عند الاختراق', 'Buy stop'],
  'tr_sellStop': ['بيع عند الكسر', 'Sell stop'],
  'tr_stopOptional': ['وقف الخسارة · اختياري', 'Stop loss · optional'],
  'tr_targetOptional': ['جني الربح · اختياري', 'Take profit · optional'],
  'tr_execute': ['تنفيذ', 'Execute'],
  'tr_checkExisting': ['فحص العملية الحالية', 'Check existing operation'],
  'tr_notSentAgain': [
    'لن تُرسل هذه العملية مرة أخرى.',
    'This operation will not be sent again.',
  ],
  'tr_price': ['السعر', 'Price'],
  // Android: the review step before every order, and its entry points.
  'tr_openOrder': ['فتح أمر', 'Open an order'],
  'tr_review': ['مراجعة الأمر', 'Review the order'],
  'tr_side': ['الاتجاه', 'Side'],
  'tr_type': ['النوع', 'Type'],
  'tr_viewMarket': ['عرض السوق', 'View the market'],
  'tr_heldSince': ['العملية الحالية منذ', 'Existing operation since'],
  'tr_liveWarning': [
    'هذا حساب وسيط وليس محاكاة: يُرسَل الأمر إلى الوسيط مباشرةً، وقد يُنفَّذ بأموال حقيقية.',
    'This is a broker account, not a simulation: the order goes straight to the broker and may execute with real money.',
  ],
  'tr_confirmNote': [
    'كل أمر من هنا أمرك أنت، ولا يُرسَل إلا بعد مراجعته وتأكيده.',
    'Every order from here is your own and is sent only after you review and confirm it.',
  ],
  'tr_pausedDown': [
    'تعذّر التحقق من حساب الوسيط الآن، فتتوقف الأوامر الجديدة وتعديلات الحماية. يبقى إغلاق الصفقات وإلغاء الأوامر المعلقة غير الحامية وتقريب وقف الخسارة متاحًا.',
    'The broker account cannot be verified right now, so new orders and protection changes are paused. Closing trades, cancelling non-protective pending orders and tightening the stop loss remain available.',
  ],
  'tr_onlyTighten': [
    'إلى أن يُتحقق من الحساب، يُقبل فقط تقريب وقف الخسارة نحو السعر أو إضافته، دون تغيير جني الربح.',
    'Until the account is verified, only moving the stop loss toward the price, or adding one, is accepted, with the take profit unchanged.',
  ],
  'tr_protectiveOrder': [
    'هذا الأمر يحمي صفقاتك المفتوحة، فلا يُلغى قبل استعادة الاتصال والتحقق.',
    'This order protects your open trades, so it cannot be cancelled until the connection is restored and checked.',
  ],
  // Android: why a typed value cannot be sent (checked before anything is sent).
  'tr_errRequired': ['هذا الحقل مطلوب.', 'This field is required.'],
  'tr_errNumber': [
    'اكتب رقمًا بالأرقام فقط، والفاصلة العشرية «.» أو «٫».',
    'Enter a number using digits only, with «.» or «٫» as the decimal point.',
  ],
  'tr_errPositive': [
    'يجب أن تكون القيمة أكبر من صفر.',
    'The value must be greater than zero.',
  ],
  'tr_errVolumeRange': [
    'يقبل الوسيط حجمًا من {0} إلى {1}.',
    'The broker accepts a volume from {0} to {1}.',
  ],
  'tr_errVolumeStep': [
    'يزيد الحجم من {0} بخطوات قدرها {1}.',
    'The volume goes up from {0} in steps of {1}.',
  ],
  'tr_errTick': [
    'يجب أن يكون السعر من مضاعفات {0}.',
    'The price must be a multiple of {0}.',
  ],
  'tr_errSymbol': ['اختر أداة مالية', 'Choose an instrument'],
  'tr_errNoChange': ['لم يتغير شيء بعد.', 'Nothing has changed yet.'],
  // Android: an answer that settles nothing, and a code without its own words.
  'tr_uncertainSend': [
    'لم يصل رد مؤكد لهذا الطلب. راجع صفقاتك ثم تحقّق من النتيجة؛ لن يُرسل بمعرّف جديد.',
    'No confirmed answer came back for this request. Check your trades, then check the result; it will not be sent under a new identity.',
  ],
  'tr_failedWithCode': [
    'تعذّر إكمال الطلب · {0}',
    'The request could not be completed · {0}',
  ],
  'tr_accountUnverified': [
    'تعذّر التحقق من حالة حساب الوسيط الآن، فلم يُرسل هذا الطلب.',
    'The broker account state could not be verified just now, so this request was not sent.',
  ],
  'tr_quoteUnusable': [
    'سعر السوق لهذه الأداة غير متاح أو قديم الآن، فلم يُرسل هذا الطلب.',
    'The market quote for this instrument is unavailable or out of date, so this request was not sent.',
  ],
  // «التعطل والاستعادة» (RecoveryPage.tsx).
  'rc_title': ['التعطل والاستعادة', 'Outage and recovery'],
  'rc_reconnecting': ['جارٍ إعادة الاتصال', 'Reconnecting'],
  'rc_reconciling': ['جارٍ التحقق مع الوسيط', 'Checking with the broker'],
  'rc_paused': ['متوقف مؤقتًا', 'Paused for now'],
  'rc_connected': ['الاتصال بالوسيط سليم', 'The broker is connected'],
  'rc_connectedBody': [
    'كل حسابات التداول المرتبطة تستجيب طبيعيًا. لا شيء موقوف.',
    'Every linked trading account answers normally. Nothing is held.',
  ],
  'rc_dropped': ['انقطع اتصال الوسيط', 'The broker connection dropped'],
  'rc_droppedBody': [
    'يتوقف التنفيذ المتأثر حتى استعادة الاتصال والتحقق.',
    'Affected execution stops until the connection is restored and checked.',
  ],
  'rc_state': ['حالة التنفيذ', 'Execution state'],
  'rc_details': ['تفاصيل الحالة', 'State details'],
  'rc_tryAgain': ['إعادة المحاولة', 'Try again'],
  'rc_since': ['منذ', 'Since'],
  'rc_lastSuccess': ['آخر قراءة ناجحة', 'Last successful read'],
  'rc_reason': ['السبب', 'Reason'],
  'rc_awaiting': ['عمليات بانتظار التأكيد', 'Operations awaiting confirmation'],
  'rc_retried': [
    'أُعيدت المحاولة. تتحدّث الحالة عندما يستجيب الوسيط.',
    'Retried. The state updates when the broker answers.',
  ],
  // Error codes worded by the Web (lib/user_error.ts).
  'broker_trading_not_allowed': [
    'لا يسمح حساب الوسيط هذا بالتداول. تحقق من صلاحياته.',
    'This broker account does not permit trading. Check its trading permissions.',
  ],
  'broker_quote_unavailable': [
    'سعر الوسيط غير متاح لهذا الرمز المحدد.',
    'The broker quote is unavailable for this exact symbol.',
  ],
  'broker_instrument_unavailable': [
    'مواصفات الوسيط غير متاحة لهذا الرمز المحدد.',
    'The broker specifications are unavailable for this exact symbol.',
  ],
  'broker_connection_changed': [
    'تغيّر اتصال الوسيط. أعد تحميله قبل المتابعة.',
    'The broker connection changed. Reload it before continuing.',
  ],
  'broker_configuration_changed': [
    'تغيّر اتصال الوسيط. أعد تحميله قبل المتابعة.',
    'The broker connection changed. Reload it before continuing.',
  ],
  'operation_already_settled': [
    'لهذه العملية نتيجة محسومة بالفعل. أعد تحميل السجل.',
    'This operation already has a settled outcome. Reload the journal.',
  ],
  'mutation_evidence_required': [
    'نتيجة العملية لدى الوسيط غير مؤكدة. يبقى التنفيذ محظورًا حتى التحقق من نتيجتها.',
    'The broker mutation is uncertain. Execution remains blocked until its result can be verified.',
  ],
  // The same words as the integrations and agent tables (L10n.register asserts identical
  // words); repeated so the order screens read them without those tables.
  'broker_disabled': [
    'اتصال الوسيط هذا معطّل.',
    'This broker connection is disabled.',
  ],
  'broker_connection_unavailable': [
    'الاتصال بالوسيط غير متاح.',
    'The broker connection is unavailable.',
  ],
  'simulation_snapshot_required': [
    'استورد بيانات السوق قبل استخدام المحاكاة.',
    'Import a market snapshot before using the simulation.',
  ],
  'invalid_request': [
    'تحقق من الحقول المطلوبة وأعد المحاولة.',
    'Check the required fields and try again.',
  ],
  'symbol_not_found': [
    'هذا الرمز غير موجود لدى الوسيط.',
    'The broker does not list this symbol.',
  ],
  // Android: the executor's refusals before anything was sent (lonora_trading.preflight,
  // execution and lonora_security.financial), and the broker's own refusal after the send.
  'broker_symbol_mismatch': [
    'الرمز لا يطابق رمز الوسيط تمامًا. لم يُرسل أي أمر.',
    'The symbol does not match the broker\'s exact symbol. Nothing was sent.',
  ],
  'volume_out_of_range': [
    'الحجم خارج الحدود التي يقبلها الوسيط لهذه الأداة. لم يُرسل أي أمر.',
    'The volume is outside the range the broker accepts for this instrument. Nothing was sent.',
  ],
  'volume_step_mismatch': [
    'الحجم لا يطابق خطوة الحجم لدى الوسيط. لم يُرسل أي أمر.',
    'The volume does not fit the broker\'s volume step. Nothing was sent.',
  ],
  'price_tick_mismatch': [
    'أحد الأسعار ليس على أصغر حركة سعرية لدى الوسيط. لم يُرسل أي أمر.',
    'A price is not on the broker\'s tick size. Nothing was sent.',
  ],
  'position_not_found': [
    'لم تعد هذه الصفقة مفتوحة لدى الوسيط. لم يُرسل أي أمر.',
    'This trade is no longer open at the broker. Nothing was sent.',
  ],
  'order_not_found': [
    'لم يعد هذا الأمر معلقًا لدى الوسيط. لم يُرسل أي أمر.',
    'This order is no longer pending at the broker. Nothing was sent.',
  ],
  'position_volume_exceeded': [
    'الحجم المطلوب أكبر من حجم الصفقة. لم يُرسل أي أمر.',
    'The requested volume is larger than the trade. Nothing was sent.',
  ],
  'position_remaining_volume_invalid': [
    'لن يطابق الحجم المتبقي من الصفقة حدود الوسيط. لم يُرسل أي أمر.',
    'The trade\'s remaining volume would not fit the broker\'s limits. Nothing was sent.',
  ],
  'unsupported_pending_order': [
    'لا يقبل الوسيط هذا النوع من الأوامر المعلقة على هذه الأداة. لم يُرسل أي أمر.',
    'The broker does not accept this kind of pending order on this instrument. Nothing was sent.',
  ],
  'market_quote_stale': [
    'سعر السوق قديم الآن، وقد تكون السوق مغلقة. لم يُرسل أي أمر.',
    'The market quote is out of date; the market may be closed. Nothing was sent.',
  ],
  'pending_price_wrong_side': [
    'سعر الأمر في الجهة الخاطئة من السعر الحالي لهذا النوع من الأوامر. لم يُرسل أي أمر.',
    'The order price is on the wrong side of the current price for this order type. Nothing was sent.',
  ],
  'stop_loss_wrong_side': [
    'وقف الخسارة في الجهة الخاطئة من السعر. لم يُرسل أي أمر.',
    'The stop loss is on the wrong side of the price. Nothing was sent.',
  ],
  'take_profit_wrong_side': [
    'جني الربح في الجهة الخاطئة من السعر. لم يُرسل أي أمر.',
    'The take profit is on the wrong side of the price. Nothing was sent.',
  ],
  'pending_stops_level': [
    'سعر الأمر أقرب إلى السعر الحالي مما يسمح به الوسيط. لم يُرسل أي أمر.',
    'The order price is closer to the current price than the broker allows. Nothing was sent.',
  ],
  'stop_loss_stops_level': [
    'وقف الخسارة أقرب إلى السعر مما يسمح به الوسيط. لم يُرسل أي أمر.',
    'The stop loss is closer to the price than the broker allows. Nothing was sent.',
  ],
  'take_profit_stops_level': [
    'جني الربح أقرب إلى السعر مما يسمح به الوسيط. لم يُرسل أي أمر.',
    'The take profit is closer to the price than the broker allows. Nothing was sent.',
  ],
  'idempotency_conflict': [
    'هذه العملية محفوظة بقيم أخرى، فلم يُرسل شيء. أعد تحميل السجل قبل المتابعة.',
    'This operation is recorded with other values, so nothing was sent. Reload the journal before continuing.',
  ],
  'operation_id_conflict': [
    'هذه العملية محفوظة بقيم أخرى، فلم يُرسل شيء. أعد تحميل السجل قبل المتابعة.',
    'This operation is recorded with other values, so nothing was sent. Reload the journal before continuing.',
  ],
  'operation_reservation_released': [
    'لم يُرسل هذا الطلب: أُلغي حجزه قبل الإرسال.',
    'This request was not sent: its reservation was released before the send.',
  ],
  'broker_unavailable_before_send': [
    'تعذّر الوصول إلى الوسيط قبل الإرسال، فلم يُرسل هذا الطلب.',
    'The broker could not be reached before the send, so this request was not sent.',
  ],
  'operation_interrupted_before_send': [
    'انقطع الطلب قبل إرساله، فلم يصل إلى الوسيط.',
    'The request was interrupted before it was sent, so it did not reach the broker.',
  ],
  'broker_request_rejected': [
    'رفض الوسيط هذا الطلب.',
    'The broker rejected this request.',
  ],
  'broker_order_rejected': [
    'رفض الوسيط هذا الأمر.',
    'The broker rejected this order.',
  ],
};
