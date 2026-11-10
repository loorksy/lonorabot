/**
 * The owner profile every agent shares: one vocabulary for Web and Mobile.
 *
 * Reach-me channels, reply languages and revision authors read the same in both
 * clients and in both languages. Delivery is in-app until off-app delivery exists,
 * and the labels say so instead of promising a notification on a closed phone.
 */

export type ReachMe = "activity" | "notify" | "message" | "call";
export const reachMeChannels: readonly ReachMe[] = ["activity", "notify", "message", "call"];
export type ReplyLanguage = "auto" | "ar" | "en";
export const replyLanguages: readonly ReplyLanguage[] = ["auto", "ar", "en"];

type Text = { readonly en: string; readonly ar: string };

const channels: Readonly<Record<ReachMe, Text>> = {
  activity: { en: "Activity only", ar: "النشاط فقط" },
  notify: { en: "Notify me", ar: "أرسل لي تنبيهًا" },
  message: { en: "Message me", ar: "راسلني" },
  call: { en: "Call me", ar: "اتصل بي" },
};

const channelHints: Readonly<Record<ReachMe, Text>> = {
  activity: {
    en: "Agents keep it in Activity and do not interrupt you.",
    ar: "يسجّل الوكلاء ذلك في النشاط ولا يقاطعونك.",
  },
  // Agents cannot raise inbox alerts of their own yet; the hint promises only what happens.
  notify: {
    en: "Agents write to you in their conversation, and alerts Lonora raises stay in your inbox.",
    ar: "يكتب لك الوكلاء في محادثتهم، وتبقى التنبيهات التي يرفعها لونورا في صندوقك.",
  },
  message: {
    en: "Agents write to you in their conversation.",
    ar: "يكتب لك الوكلاء في محادثتهم.",
  },
  call: {
    en: "Agents can ring this device when your decision is needed, outside quiet hours.",
    ar: "يمكن للوكلاء الاتصال بهذا الجهاز عند الحاجة إلى قرارك، خارج أوقات الهدوء.",
  },
};

const languages: Readonly<Record<ReplyLanguage, Text>> = {
  auto: { en: "The language of my latest message", ar: "لغة آخر رسالة مني" },
  ar: { en: "Arabic", ar: "العربية" },
  en: { en: "English", ar: "الإنجليزية" },
};

const labels = {
  title: { en: "About you", ar: "عنك" },
  shared: {
    en: "Every agent reads this profile. Each change keeps who made it, and you can undo any change; later changes stay.",
    ar: "يقرأ كل وكيل هذا الملف. يُحفظ مع كل تغيير من أجراه، ويمكنك التراجع عن أي تغيير مع بقاء التغييرات اللاحقة.",
  },
  profile: { en: "What agents know about you", ar: "ما يعرفه الوكلاء عنك" },
  reachMe: { en: "How to reach you", ar: "كيف نتواصل معك" },
  replyLanguage: { en: "Reply language", ar: "لغة الردود" },
  inAppOnly: {
    en: "Delivered inside Lonora for now; alerts on a closed phone are not set up yet.",
    ar: "يصل داخل لونورا حاليًا؛ التنبيهات على هاتف مغلق غير مهيأة بعد.",
  },
  device: { en: "Device to ring", ar: "الجهاز الذي يرن" },
  noDevice: {
    en: "Register a device with your passkey before choosing calls.",
    ar: "سجّل جهازًا بمفتاح المرور قبل اختيار الاتصال.",
  },
  quietHours: { en: "Quiet hours", ar: "أوقات الهدوء" },
  quietStart: { en: "From (hour 0–23)", ar: "من (الساعة 0–23)" },
  quietEnd: { en: "Until (hour 0–23)", ar: "حتى (الساعة 0–23)" },
  actionRequiredCalls: { en: "Call when my decision is needed", ar: "اتصل عند الحاجة إلى قراري" },
  opportunityCalls: { en: "Also call for opportunities", ar: "اتصل أيضًا عند الفرص" },
  save: { en: "Save", ar: "حفظ" },
  saved: { en: "Saved", ar: "تم الحفظ" },
  history: { en: "Changes", ar: "التغييرات" },
  noHistory: { en: "No changes yet.", ar: "لا توجد تغييرات بعد." },
  restore: { en: "Undo this change", ar: "تراجع عن هذا التغيير" },
  restoreSettings: {
    en: "Undo this change to your settings",
    ar: "تراجع عن هذا التغيير في إعداداتك",
  },
  restored: {
    en: "Undone. Later changes were kept.",
    ar: "تم التراجع، وبقيت التغييرات اللاحقة.",
  },
  byOwner: { en: "You", ar: "أنت" },
  bySystem: { en: "Lonora, when profiles were merged", ar: "لونورا، عند دمج الملفات" },
  removedAgent: { en: "A removed agent", ar: "وكيل محذوف" },
  fromYourMessage: { en: "from your message", ar: "من رسالتك" },
  restoredChange: { en: "undid an earlier change", ar: "تراجع عن تغيير سابق" },
  added: { en: "Added", ar: "أُضيف" },
  removed: { en: "Removed", ar: "حُذف" },
  more: { en: "More lines changed", ar: "تغيّرت أسطر أخرى" },
  notSet: { en: "Not set", ar: "غير محدد" },
  on: { en: "On", ar: "مفعّل" },
  off: { en: "Off", ar: "متوقف" },
} as const satisfies Record<string, Text>;

const fields: Readonly<Record<string, Text>> = {
  name: { en: "Name", ar: "الاسم" },
  address: { en: "Form of address", ar: "طريقة المخاطبة" },
  reply_language: { en: "Reply language", ar: "لغة الردود" },
  reach_me: { en: "How to reach you", ar: "كيف نتواصل معك" },
  quiet_hours: { en: "Quiet hours", ar: "أوقات الهدوء" },
  timezone: { en: "Time zone", ar: "المنطقة الزمنية" },
  opportunity_calls: { en: "Calls for opportunities", ar: "الاتصال عند الفرص" },
  action_required_calls: {
    en: "Calls when your input is needed",
    ar: "الاتصال عند الحاجة إلى ردك",
  },
};

const errors: Readonly<Record<string, Text>> = {
  memory_user_section_moved: {
    en: "Preferences about you now live in your profile under Knowledge, shared by every agent. Remove the USER.md section here and add it to your profile.",
    ar: "أصبحت تفضيلاتك في ملفك ضمن المعرفة، ويشترك فيه كل الوكلاء. احذف قسم USER.md من هنا وأضفه إلى ملفك.",
  },
  owner_profile_too_large: {
    en: "Your profile is too long. Shorten or summarize it and save again.",
    ar: "ملفك طويل جدًا. اختصره أو لخّصه ثم احفظ مجددًا.",
  },
  memory_revision_not_found: {
    en: "This change is no longer in the history. Reload the list.",
    ar: "لم يعد هذا التغيير في السجل. حدّث القائمة.",
  },
  incoming_call_channel_conflict: {
    en: "Choose one way to reach you, then save again.",
    ar: "اختر طريقة واحدة للتواصل معك ثم احفظ مجددًا.",
  },
  incoming_call_device_required: {
    en: "Register a device with your passkey before choosing calls.",
    ar: "سجّل جهازًا بمفتاح المرور قبل اختيار الاتصال.",
  },
  incoming_call_device_unavailable: {
    en: "The chosen device is no longer registered. Choose another device or another way to reach you.",
    ar: "لم يعد الجهاز المختار مسجلًا. اختر جهازًا آخر أو طريقة أخرى للتواصل معك.",
  },
  incoming_call_quiet_hours_incomplete: {
    en: "Set both the start and the end of quiet hours, or clear both.",
    ar: "حدّد بداية أوقات الهدوء ونهايتها معًا، أو امسحهما معًا.",
  },
  incoming_call_quiet_hours_empty: {
    en: "Quiet hours must start and end at different times.",
    ar: "يجب أن تبدأ ساعات الهدوء وتنتهي في وقتين مختلفين.",
  },
  invalid_timezone: {
    en: "Choose a valid time zone, such as Asia/Riyadh.",
    ar: "اختر منطقة زمنية صحيحة، مثل Asia/Riyadh.",
  },
  memory_revert_conflict: {
    en: "A later change edited the same lines, so nothing was undone. Undo that later change first, or edit the text directly.",
    ar: "عدّل تغيير لاحق الأسطر نفسها، فلم يُتراجع عن شيء. تراجع عن ذلك التغيير اللاحق أولًا، أو عدّل النص مباشرة.",
  },
};

function pick(text: Text, locale: string): string {
  return locale.startsWith("ar") ? text.ar : text.en;
}

export type OwnerProfileLabel = keyof typeof labels;

export function ownerProfileLabel(key: OwnerProfileLabel, locale: string): string {
  return pick(labels[key], locale);
}

export function reachMeLabel(channel: ReachMe, locale: string): string {
  return pick(channels[channel], locale);
}

export function reachMeHint(channel: ReachMe, locale: string): string {
  return pick(channelHints[channel], locale);
}

export function replyLanguageLabel(language: ReplyLanguage, locale: string): string {
  return pick(languages[language], locale);
}

export function preferenceFieldLabel(field: string, locale: string): string | null {
  const text = fields[field];
  return text ? pick(text, locale) : null;
}

/** A recorded preference value in plain words; device identifiers are never shown. */
export function preferenceValueText(field: string, value: unknown, locale: string): string {
  if (value === null || value === undefined || value === "") return pick(labels.notSet, locale);
  if (typeof value === "boolean") return pick(value ? labels.on : labels.off, locale);
  if (field === "reach_me" && typeof value === "string" && value in channels)
    return pick(channels[value as ReachMe], locale);
  if (field === "reply_language" && (value === "ar" || value === "en"))
    return pick(languages[value], locale);
  return String(value);
}

/** Owner text for a profile or memory error code, or null for other codes. */
export function ownerProfileError(code: string, locale: string): string | null {
  const text = errors[code];
  return text ? pick(text, locale) : null;
}

export const ownerProfileLabelKeys = Object.keys(labels) as OwnerProfileLabel[];
