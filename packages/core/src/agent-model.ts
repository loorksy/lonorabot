/**
 * An agent's model, shared by Web and Mobile: the model card in an agent's settings.
 * Only the owner assigns a model (here, or by naming one in chat); a new agent starts on
 * Lonora's model. Only server facts are shown; model and agent names are isolated so
 * they keep their order inside Arabic text. Choosing a model never grants authority and
 * never repeats anything.
 */
import type { AgentModelSummary, ModelLabel } from "@lonora/contracts";
import { isolate } from "./trading-readiness";

type Language = "ar" | "en";

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

export const agentModelLabels = {
  en: {
    title: "Model",
    ownerOnly: "Only you choose its model: here, or by naming one in chat.",
    chooseModel: "Choose a model",
    backToDefault: "Back to your default model",
    defaultModel: "your default model",
    answering: "Answering now",
    chosenByYou: "Chosen by you",
    inherited: "Lonora's model when it was created",
    save: "Save model",
    saved: "Saved",
    noModels: "Connect a provider and discover its models in Model settings first.",
    usageDays: "Last {days} days",
    usageLine: "{input} in · {output} out · {requests} requests",
    noUsage: "No model use in the last {days} days.",
    usageTitle: "Usage per agent",
    usageHint: "Tokens your agents used. There is no spending cap.",
    agent: "Agent",
    unattributed: "Not tied to an agent",
  },
  ar: {
    title: "النموذج",
    ownerOnly: "أنت وحدك تختار نموذجه: من هنا، أو بتسمية نموذج في المحادثة.",
    chooseModel: "اختر نموذجًا",
    backToDefault: "العودة إلى نموذجك الافتراضي",
    defaultModel: "نموذجك الافتراضي",
    answering: "يجيب الآن",
    chosenByYou: "اخترته أنت",
    inherited: "نموذج لونورا عند إنشائه",
    save: "حفظ النموذج",
    saved: "حُفظ",
    noModels: "صِل مزوّدًا واكتشف نماذجه في إعدادات النماذج أولًا.",
    usageDays: "آخر {days} يومًا",
    usageLine: "{input} دخل · {output} خرج · {requests} طلب",
    noUsage: "لا استخدام للنماذج في آخر {days} يومًا.",
    usageTitle: "الاستخدام لكل وكيل",
    usageHint: "الرموز التي استخدمها وكلاؤك. لا يوجد سقف للإنفاق.",
    agent: "الوكيل",
    unattributed: "غير مرتبط بوكيل",
  },
} as const satisfies Record<Language, Record<string, string>>;
export type AgentModelText = (typeof agentModelLabels)[Language];

export function agentModelText(locale: string): AgentModelText {
  return agentModelLabels[language(locale)];
}

function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => values[key] ?? "");
}

/** A model's name as the owner recognizes it, isolated for Arabic text; null if none. */
export function modelName(label: ModelLabel | null | undefined): string | null {
  const name = label?.name ?? label?.model;
  return name ? isolate(name) : null;
}

/** A token count the owner can read at a glance ("12.3K", "١٢٫٣ ألف"). */
export function tokenCount(value: number, locale: string): string {
  return new Intl.NumberFormat(language(locale) === "ar" ? "ar" : "en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/** One agent's usage line, or the "no use" line; never a cap (owner decision D4). */
export function usageLine(
  usage: { input_tokens: number; output_tokens: number; requests: number },
  days: number,
  locale: string,
): string {
  const text = agentModelText(locale);
  const count = new Intl.NumberFormat(language(locale) === "ar" ? "ar" : "en").format(days);
  if (!usage.requests) return fill(text.noUsage, { days: count });
  return `${fill(text.usageDays, { days: count })}: ${fill(text.usageLine, {
    input: isolate(tokenCount(usage.input_tokens, locale)),
    output: isolate(tokenCount(usage.output_tokens, locale)),
    requests: isolate(
      new Intl.NumberFormat(language(locale) === "ar" ? "ar" : "en").format(usage.requests),
    ),
  })}`;
}

/** Whether the agent answers on a model someone set rather than the owner's default:
 * then Web and Mobile both offer "Back to your default model". */
export function offersDefaultModel(summary: AgentModelSummary): boolean {
  return summary.record.preference.primary != null;
}

/** The model card's summary lines in an agent's settings. */
export function agentModelLines(summary: AgentModelSummary, locale: string): string[] {
  const text = agentModelText(locale);
  const record = summary.record;
  const lines = [`${text.answering}: ${modelName(summary.current) ?? text.defaultModel}`];
  if (record.chosen_by && record.preference.primary)
    lines.push(record.chosen_by === "owner" ? text.chosenByYou : text.inherited);
  lines.push(usageLine(summary.usage, summary.usage.days, locale));
  return lines;
}
