/** The owner's words for each trade action, the same on Web and Mobile. */
export const tradeActionLabels = {
  en: {
    buy: "Market buy",
    sell: "Market sell",
    buy_limit: "Buy limit",
    sell_limit: "Sell limit",
    buy_stop: "Buy stop",
    sell_stop: "Sell stop",
    close_position: "Close position",
    modify_position: "Modify position",
    cancel_order: "Cancel pending order",
    modify_order: "Modify pending order",
  },
  ar: {
    buy: "شراء سوقي",
    sell: "بيع سوقي",
    buy_limit: "شراء محدد",
    sell_limit: "بيع محدد",
    buy_stop: "شراء إيقاف",
    sell_stop: "بيع إيقاف",
    close_position: "إغلاق صفقة",
    modify_position: "تعديل صفقة",
    cancel_order: "إلغاء أمر معلّق",
    modify_order: "تعديل أمر معلّق",
  },
} as const;
