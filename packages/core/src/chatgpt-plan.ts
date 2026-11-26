/**
 * Sign in with ChatGPT (VISION Amendment 4), shared by Web and Mobile: the Secret card's two
 * steps, the address the owner pastes, the connected account, "Using ChatGPT plan" with
 * Manage usage, sign-out, the plan's limit and the sign-in's errors, in Arabic and English.
 * Every value the owner pastes goes only to the card's own route; nothing here keeps one.
 */
import type { OwnerAction } from "@lonora/contracts";
import { isolate } from "./trading-readiness";

type Language = "ar" | "en";

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

/** The ChatGPT plan's provider id. */
export const CHATGPT_PROVIDER = "openai_chatgpt";
/** ChatGPT settings › Usage: where the owner reviews the plan's use and Lonora's access. */
export const MANAGE_USAGE_URL = "https://chatgpt.com/settings/usage";

export const chatgptLabels = {
  en: {
    name: "ChatGPT",
    title: "Use your ChatGPT plan",
    plan: "Eligible requests use your ChatGPT Plus or Pro plan, managed in ChatGPT settings.",
    stepSignIn: "1. Continue with ChatGPT, sign in and allow Lonora to use your plan.",
    stepPaste:
      "2. You will reach a page that does not open. Copy its whole address from the address bar and paste it here.",
    hint: "The sign-in is kept encrypted on your Lonora server. It never enters the chat, and no agent sees it.",
    continue: "Continue with ChatGPT",
    address: "The page's address",
    connect: "Connect",
    continuingAs: "Signing in as {account}.",
    otherAccount: "Use a different ChatGPT account",
    connected: "Connected: {account}",
    connectedNoAccount: "Connected to your ChatGPT plan.",
    usingPlan: "Using ChatGPT plan",
    planNotUsed: "Signed in, but Lonora is not using your ChatGPT plan.",
    manageUsage: "Manage usage",
    signOut: "Sign out",
    signedOut: "Signed out. Lonora no longer uses your ChatGPT plan.",
    revocationUnconfirmed:
      "Signed out on your server, but OpenAI did not confirm it. To end Lonora's access there, disconnect it in ChatGPT settings.",
    signInAgain: "Sign in with ChatGPT again to keep using your plan.",
    planLimitTitle: "ChatGPT plan limit reached",
    planLimitLine:
      "Your ChatGPT plan, or its limit for Lonora, is used up for now. Review it in ChatGPT settings, or choose another model.",
  },
  ar: {
    name: "ChatGPT",
    title: "استخدم اشتراك ChatGPT",
    plan: "تستخدم الطلبات المؤهلة اشتراك ChatGPT Plus أو Pro الخاص بك، وتُدار من إعدادات ChatGPT.",
    stepSignIn: "١. تابع باستخدام ChatGPT، وسجّل الدخول، واسمح للونورا باستخدام اشتراكك.",
    stepPaste: "٢. ستصل إلى صفحة لا تفتح. انسخ عنوانها كاملاً من شريط العنوان والصقه هنا.",
    hint: "يُحفظ تسجيل الدخول مشفّرًا على خادم لونورا. لا يدخل المحادثة، ولا يراه أي وكيل.",
    continue: "المتابعة باستخدام ChatGPT",
    address: "عنوان الصفحة",
    connect: "ربط",
    continuingAs: "تسجيل الدخول باسم {account}.",
    otherAccount: "استخدم حساب ChatGPT آخر",
    connected: "متصل: {account}",
    connectedNoAccount: "متصل باشتراك ChatGPT.",
    usingPlan: "يستخدم اشتراك ChatGPT",
    planNotUsed: "مسجّل الدخول، لكن لونورا لا تستخدم اشتراك ChatGPT.",
    manageUsage: "إدارة الاستخدام",
    signOut: "تسجيل الخروج",
    signedOut: "تم تسجيل الخروج. لم تعد لونورا تستخدم اشتراك ChatGPT.",
    revocationUnconfirmed:
      "سُجّل الخروج على خادمك، لكن OpenAI لم تؤكد ذلك. لإنهاء وصول لونورا هناك، افصلها من إعدادات ChatGPT.",
    signInAgain: "سجّل الدخول باستخدام ChatGPT مجددًا لتواصل استخدام اشتراكك.",
    planLimitTitle: "بلغت حد اشتراك ChatGPT",
    planLimitLine:
      "استُنفد اشتراك ChatGPT أو حدّه المخصص للونورا حاليًا. راجعه من إعدادات ChatGPT، أو اختر نموذجًا آخر.",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type ChatGptText = (typeof chatgptLabels)[Language];

export function chatgptText(locale: string): ChatGptText {
  return chatgptLabels[language(locale)];
}

/** The card's sign-in while it waits: the button, the paste field and its submit, and the
 * owner's choice to register another account than the one Lonora continues. */
export type ChatGptSignInForm = {
  continue: string;
  address: string;
  submit: string;
  otherAccount: string;
};

/** A Secret card that signs in with ChatGPT instead of taking a key. */
export function isChatGptCard(card: OwnerAction): boolean {
  const secret = card.facts.secret;
  return (
    card.kind === "secret" &&
    secret?.connect === "model_provider" &&
    secret.details?.provider === CHATGPT_PROVIDER
  );
}

/** One attempt: OpenAI's sign-in address to open in the browser, and the registered account
 * it continues (null for a new registration). */
export type ChatGptStart = {
  authorization_url: string;
  expires_at: string;
  account: string | null;
};

/** OpenAI's sign-in address for one attempt; ``newAccount`` is "Use a different ChatGPT
 * account": a new registration, which replaces the saved one once it is verified. */
export async function startChatGptSignIn(
  post: (path: string, body: unknown) => Promise<ChatGptStart>,
  cardId: string,
  newAccount = false,
): Promise<ChatGptStart> {
  return post(
    `/owner-actions/${encodeURIComponent(cardId)}/chatgpt/start`,
    newAccount ? { new_account: true } : {},
  );
}

/** "Signing in as …" once an attempt continues a registered account; null for a new one. */
export function continuingAsLine(
  account: string | null | undefined,
  locale: string,
): string | null {
  return account ? chatgptText(locale).continuingAs.replace("{account}", isolate(account)) : null;
}

/** The address the browser landed on, pasted by the owner: the card as it settled. */
export async function finishChatGptSignIn<Card>(
  post: (path: string, body: unknown) => Promise<Card>,
  cardId: string,
  address: string,
): Promise<Card> {
  return post(`/owner-actions/${encodeURIComponent(cardId)}/chatgpt/finish`, {
    address: address.trim(),
  });
}

export type ChatGptSignOut = { signed_out: boolean; revoked: boolean };

export async function signOutChatGpt(
  post: (path: string, body: unknown) => Promise<ChatGptSignOut>,
): Promise<ChatGptSignOut> {
  return post("/providers/openai_chatgpt/sign-out", {});
}

/** The ChatGPT sign-in as the providers list reads it (``GET /providers``): never a token. */
export type ChatGptStatus = {
  email: string | null;
  plan: boolean;
  sign_in_again: boolean;
  signed_in?: boolean;
};

/** The providers list's ChatGPT row: its line, and whether Sign out is offered (whenever a
 * sign-in holds tokens, plan use allowed or not); null when there is nothing to show. */
export function chatgptRow(
  status: ChatGptStatus | null | undefined,
  locale: string,
): { line: string; signOut: boolean } | null {
  if (!status) return null;
  const text = chatgptText(locale);
  const signOut = Boolean(status.signed_in);
  if (status.plan) return { line: text.usingPlan, signOut };
  if (status.sign_in_again) return { line: text.signInAgain, signOut };
  if (signOut) return { line: text.planNotUsed, signOut };
  return null;
}

/** What sign-out did: confirmed at OpenAI, or only on the owner's server. */
export function signOutLine(result: ChatGptSignOut, locale: string): string {
  const text = chatgptText(locale);
  return result.revoked ? text.signedOut : text.revocationUnconfirmed;
}

/** A run that failed on the ChatGPT plan's own limit: shown as the plan's, with Manage usage. */
export function planLimitReached(
  failure: { family?: string; provider?: string | null } | null | undefined,
): boolean {
  return failure?.family === "quota" && failure.provider === CHATGPT_PROVIDER;
}

const errors: Readonly<Record<string, { en: string; ar: string }>> = {
  chatgpt_sign_in_unavailable: {
    en: "This Lonora does not offer Sign in with ChatGPT. Connect an OpenAI API key instead.",
    ar: "لا تتيح لونورا هذه تسجيل الدخول باستخدام ChatGPT. اربط مفتاح OpenAI API بدلًا منه.",
  },
  chatgpt_sign_in_required: {
    en: "This card signs in with ChatGPT: tap Continue with ChatGPT.",
    ar: "هذه البطاقة تسجّل الدخول باستخدام ChatGPT: اضغط المتابعة باستخدام ChatGPT.",
  },
  chatgpt_sign_in_expired: {
    en: "This sign-in is no longer waiting. Tap Continue with ChatGPT to start again.",
    ar: "لم يعد تسجيل الدخول هذا بانتظارك. اضغط المتابعة باستخدام ChatGPT للبدء من جديد.",
  },
  chatgpt_address_invalid: {
    en: "This is not the address of that page. Copy the whole address from the address bar, starting with http://127.0.0.1:1455/auth/callback.",
    ar: "هذا ليس عنوان تلك الصفحة. انسخ العنوان كاملًا من شريط العنوان، وهو يبدأ بـ http://127.0.0.1:1455/auth/callback.",
  },
  chatgpt_state_mismatch: {
    en: "This address is from another sign-in. Paste the address of the last one you started.",
    ar: "هذا العنوان من تسجيل دخول آخر. الصق عنوان آخر تسجيل دخول بدأته.",
  },
  chatgpt_sign_in_declined: {
    en: "Lonora was not approved in ChatGPT. Tap Continue with ChatGPT to try again.",
    ar: "لم تتم الموافقة على لونورا في ChatGPT. اضغط المتابعة باستخدام ChatGPT للمحاولة مجددًا.",
  },
  chatgpt_sign_in_failed: {
    en: "ChatGPT could not finish this sign-in. Nothing was saved. Start again.",
    ar: "تعذّر على ChatGPT إتمام تسجيل الدخول هذا. لم يُحفظ شيء. ابدأ من جديد.",
  },
  chatgpt_sign_in_code_expired: {
    en: "This sign-in was already used or took too long. Tap Continue with ChatGPT again.",
    ar: "استُخدم تسجيل الدخول هذا من قبل أو طال وقته. اضغط المتابعة باستخدام ChatGPT مجددًا.",
  },
  chatgpt_client_mismatch: {
    en: "ChatGPT answered for another registration of Lonora. Nothing was saved. Start again.",
    ar: "أجاب ChatGPT لتسجيل آخر للونورا. لم يُحفظ شيء. ابدأ من جديد.",
  },
  chatgpt_identity_invalid: {
    en: "ChatGPT's answer could not be verified. Nothing was saved. Start again.",
    ar: "تعذّر التحقق من إجابة ChatGPT. لم يُحفظ شيء. ابدأ من جديد.",
  },
  chatgpt_other_account: {
    en: "You signed in with another ChatGPT account than the one Lonora is registered with. Sign in with that account, or tap Use a different ChatGPT account.",
    ar: "سجّلت الدخول بحساب ChatGPT غير الحساب المسجّلة به لونورا. سجّل الدخول بذلك الحساب، أو اضغط استخدم حساب ChatGPT آخر.",
  },
  chatgpt_plan_use_declined: {
    en: "You signed in, but did not allow Lonora to use your plan. Tap Continue with ChatGPT and allow it, or connect an OpenAI API key.",
    ar: "سجّلت الدخول لكنك لم تسمح للونورا باستخدام اشتراكك. اضغط المتابعة باستخدام ChatGPT واسمح بذلك، أو اربط مفتاح OpenAI API.",
  },
  chatgpt_unreachable: {
    en: "Lonora could not reach ChatGPT. Tap Continue with ChatGPT to start again shortly.",
    ar: "تعذّر على لونورا الوصول إلى ChatGPT. اضغط المتابعة باستخدام ChatGPT للبدء من جديد بعد قليل.",
  },
  owner_action_not_chatgpt: {
    en: "This card does not sign in with ChatGPT.",
    ar: "هذه البطاقة لا تسجّل الدخول باستخدام ChatGPT.",
  },
};

/** Owner text for a sign-in refusal; null if the code is not one. */
export function chatgptError(code: string | null | undefined, locale: string): string | null {
  const entry = code ? errors[code] : undefined;
  return entry ? entry[language(locale)] : null;
}
