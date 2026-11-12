/**
 * Supervision on the agents' profiles: one shared label table and row model for Web and
 * Mobile (lonora_db.supervision). A grant lets one agent read and steer another's work
 * and never carries money authority; the owner stops any grant with one tap. Names are
 * isolated so a Latin name keeps its order inside Arabic text.
 */
import type { SupervisionGrant, SupervisionView } from "@lonora/contracts";
import { isolate } from "./trading-readiness";

type Language = "ar" | "en";

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

export const supervisionLabels = {
  en: {
    title: "Supervision",
    personalTitle: "Lonora supervises your agents",
    personalIntro:
      "Lonora reads each agent's work and memory, messages it and can pause or resume its work. It never trades for them, never uses their grant and never lifts your brakes.",
    intro:
      "A supervisor reads this agent's work and memory, messages it and can pause or resume its work. It never trades for it or lifts your brakes.",
    supervisedBy: "Supervised by",
    supervises: "Supervises",
    stop: "Stop",
    byDefault: "by default",
    byYou: "set by you",
    fromMessage: "from your message",
    fromCard: "from a card",
    none: "Lonora leads this agent by its role. No other agent supervises it, and it supervises none.",
    unnamed: "An agent",
  },
  ar: {
    title: "الإشراف",
    personalTitle: "لونورا تشرف على وكلائك",
    personalIntro:
      "تقرأ لونورا عمل كل وكيل وذاكرته، وتراسله، وتستطيع إيقاف عمله أو استئنافه. لا تتداول عنهم أبدًا، ولا تستخدم تفويضهم، ولا ترفع فراملك.",
    intro:
      "يقرأ المشرف عمل هذا الوكيل وذاكرته، ويراسله، ويستطيع إيقاف عمله أو استئنافه. لا يتداول عنه أبدًا ولا يرفع فراملك.",
    supervisedBy: "يشرف عليه",
    supervises: "يشرف على",
    stop: "إيقاف",
    byDefault: "افتراضيًا",
    byYou: "عيّنته أنت",
    fromMessage: "من رسالتك",
    fromCard: "من بطاقة",
    none: "تقود لونورا هذا الوكيل بدورها. لا يشرف عليه أي وكيل آخر، ولا يشرف هو على أحد.",
    unnamed: "وكيل",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type SupervisionText = (typeof supervisionLabels)[Language];

export function supervisionText(locale: string): SupervisionText {
  return supervisionLabels[language(locale)];
}

/** One grant as a row: the other agent's name and where the grant came from. */
export type SupervisionRow = { grantId: string; agentId: string; name: string; source: string };

function source(grant: SupervisionGrant, text: SupervisionText): string {
  switch (grant.created_via) {
    case "default":
      return text.byDefault;
    case "owner_ui":
      return text.byYou;
    case "owner_message":
      return text.fromMessage;
    case "owner_card":
      return text.fromCard;
  }
}

/** Whom the agent supervises and who supervises it, ready to render with dir="auto". */
export function supervisionRows(
  view: SupervisionView,
  locale: string,
): { supervises: SupervisionRow[]; supervisedBy: SupervisionRow[] } {
  const text = supervisionText(locale);
  const row = (grant: SupervisionGrant, other: SupervisionGrant["supervisor"]) => ({
    grantId: grant.id,
    agentId: other.id,
    name: other.name ? isolate(other.name) : text.unnamed,
    source: source(grant, text),
  });
  return {
    supervises: view.supervises.map((grant) => row(grant, grant.supervised)),
    supervisedBy: view.supervised_by.map((grant) => row(grant, grant.supervisor)),
  };
}

const errors: Readonly<Record<string, { en: string; ar: string }>> = {
  supervision_grant_not_found: {
    en: "This supervision no longer exists.",
    ar: "لم يعد هذا الإشراف موجودًا.",
  },
  supervision_self_target: {
    en: "An agent cannot supervise itself.",
    ar: "لا يمكن للوكيل أن يشرف على نفسه.",
  },
  supervision_supervisor_invalid: {
    en: "A temporary helper cannot supervise other agents.",
    ar: "لا يستطيع المساعد المؤقت الإشراف على وكلاء آخرين.",
  },
};

/** Owner text for a supervision refusal, shared by Web and Mobile; null if not one. */
export function supervisionError(code: string | null | undefined, locale: string): string | null {
  const entry = code ? errors[code] : undefined;
  return entry ? entry[language(locale)] : null;
}
