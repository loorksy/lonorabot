/**
 * An agent's model, shared by Web and Mobile (W15-10): the model card in an agent's
 * settings and the two model cards in the conversation ("Change its model?" and the
 * Undo card after a switch). Only server facts are shown; model and agent names are
 * isolated so they keep their order inside Arabic text. Choosing a model never grants
 * authority and never repeats anything.
 */
import type {
  AgentModelMode,
  AgentModelSummary,
  ModelLabel,
  OwnerAction,
  OwnerActionModelState,
} from "@lonora/contracts";
import { isolate } from "./trading-readiness";

type Language = "ar" | "en";

function language(locale: string): Language {
  return locale.startsWith("ar") ? "ar" : "en";
}

export const agentModelLabels = {
  en: {
    title: "Model",
    automatic: "Automatic",
    automaticHint:
      "Lonora chooses: your default model, and this agent may switch itself among your allowed models.",
    fixed: "Fixed",
    fixedHint: "Always this model; only you change it.",
    chooseModel: "Choose a model",
    backToDefault: "Back to your default model",
    defaultModel: "your default model",
    now: "Now",
    answering: "Answering now",
    chosenByYou: "Chosen by you",
    chosenByAgent: "Set by the agent",
    allowed: "Models it may choose on its own",
    allowedTitle: "Models your agents may choose",
    allowedHint:
      "Your default model and backups are always included. Agents switch among these on their own; any other model is a one-tap card.",
    add: "Add",
    remove: "Remove",
    save: "Save",
    saved: "Saved",
    noModels: "Connect a provider and discover its models in Model settings first.",
    usageDays: "Last {days} days",
    usageLine: "{input} in · {output} out · {requests} requests",
    noUsage: "No model use in the last {days} days.",
    usageTitle: "Usage per agent",
    usageHint: "Tokens your agents used. There is no spending cap.",
    agent: "Agent",
    unattributed: "Not tied to an agent",
    requestTitle: "Change the model of {agent}?",
    thisAgent: "this agent",
    requested: "Asked for",
    keptUntil: "kept until you change it",
    mayChangeAgain: "Lonora may switch again among your allowed models",
    joinsList: "{model} joins the models your agents may choose.",
    askedBy: "Asked by {agent}",
    unchanged: "Memory, tasks, grants and open trades stay as they are; nothing is repeated.",
    useIt: "Use it",
    letLonora: "Let Lonora choose",
    notNow: "Not now",
    switchedTitle: "{agent} switched its model",
    undo: "Undo",
    keep: "Keep",
    done: "Done. {agent} now uses {model}.",
    undone: "Undone. The previous model is back.",
    kept: "Kept.",
    dismissed: "Dismissed. Nothing changed.",
    expired: "This card expired. Nothing changed.",
    alreadySet: "Already set. Nothing changed.",
    ownerChanged: "You chose this agent's model since. Nothing else changed.",
    changedAgain: "Its model changed again since. Nothing changed.",
    noLongerApplies: "This no longer applies. Nothing changed.",
  },
  ar: {
    title: "النموذج",
    automatic: "تلقائي",
    automaticHint:
      "تختار لونورا: نموذجك الافتراضي، ويمكن لهذا الوكيل أن ينتقل بنفسه بين النماذج التي سمحت بها.",
    fixed: "ثابت",
    fixedHint: "هذا النموذج دائمًا؛ لا يغيّره إلا أنت.",
    chooseModel: "اختر نموذجًا",
    backToDefault: "العودة إلى نموذجك الافتراضي",
    defaultModel: "نموذجك الافتراضي",
    now: "الآن",
    answering: "يجيب الآن",
    chosenByYou: "اخترته أنت",
    chosenByAgent: "ضبطه الوكيل",
    allowed: "نماذج يختار بينها وحده",
    allowedTitle: "النماذج التي يختار بينها وكلاؤك",
    allowedHint:
      "نموذجك الافتراضي والاحتياطية مشمولة دائمًا. ينتقل الوكلاء بين هذه وحدهم؛ وأي نموذج آخر بطاقة بلمسة واحدة.",
    add: "إضافة",
    remove: "إزالة",
    save: "حفظ",
    saved: "حُفظ",
    noModels: "صِل مزوّدًا واكتشف نماذجه في إعدادات النماذج أولًا.",
    usageDays: "آخر {days} يومًا",
    usageLine: "{input} دخل · {output} خرج · {requests} طلب",
    noUsage: "لا استخدام للنماذج في آخر {days} يومًا.",
    usageTitle: "الاستخدام لكل وكيل",
    usageHint: "الرموز التي استخدمها وكلاؤك. لا يوجد سقف للإنفاق.",
    agent: "الوكيل",
    unattributed: "غير مرتبط بوكيل",
    requestTitle: "تغيير نموذج {agent}؟",
    thisAgent: "هذا الوكيل",
    requested: "المطلوب",
    keptUntil: "يبقى حتى تغيّره",
    mayChangeAgain: "قد تنتقل لونورا مجددًا بين النماذج التي سمحت بها",
    joinsList: "ينضم {model} إلى النماذج التي يختار بينها وكلاؤك.",
    askedBy: "طلبه {agent}",
    unchanged: "الذاكرة والمهام والتفويضات والصفقات المفتوحة باقية كما هي؛ ولا يُعاد شيء.",
    useIt: "استخدمه",
    letLonora: "دع لونورا تختار",
    notNow: "ليس الآن",
    switchedTitle: "غيّر {agent} نموذجه",
    undo: "تراجع",
    keep: "إبقاء",
    done: "تم. يستخدم {agent} الآن {model}.",
    undone: "تم التراجع. عاد النموذج السابق.",
    kept: "أُبقي.",
    dismissed: "أُغلقت. لم يتغير شيء.",
    expired: "انتهت صلاحية هذه البطاقة. لم يتغير شيء.",
    alreadySet: "مضبوط بالفعل. لم يتغير شيء.",
    ownerChanged: "اخترت نموذج هذا الوكيل بعدها. لم يتغير شيء آخر.",
    changedAgain: "تغيّر نموذجه مجددًا بعدها. لم يتغير شيء.",
    noLongerApplies: "لم تعد هذه البطاقة سارية. لم يتغير شيء.",
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

/** "Automatic · your default model (GPT-5)", "Automatic · Claude Sonnet", "Fixed · Opus". */
export function modelChoiceLine(
  state: { mode: AgentModelMode; model: ModelLabel | null | undefined },
  defaultModel: ModelLabel | null | undefined,
  locale: string,
): string {
  const text = agentModelText(locale);
  const mode = state.mode === "fixed" ? text.fixed : text.automatic;
  const chosen = modelName(state.model);
  if (chosen) return `${mode} · ${chosen}`;
  const fallback = modelName(defaultModel);
  return fallback
    ? `${mode} · ${text.defaultModel} (${fallback})`
    : `${mode} · ${text.defaultModel}`;
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

/**
 * Whether an Automatic agent answers on a model someone set rather than the owner's
 * default: then Web and Mobile both offer "Back to your default model".
 */
export function offersDefaultModel(summary: AgentModelSummary): boolean {
  return summary.record.mode === "automatic" && summary.record.preference.primary != null;
}

/** The model card's summary lines in an agent's settings. */
export function agentModelLines(summary: AgentModelSummary, locale: string): string[] {
  const text = agentModelText(locale);
  const record = summary.record;
  const lines = [`${text.answering}: ${modelName(summary.current) ?? text.defaultModel}`];
  if (record.chosen_by && record.preference.primary)
    lines.push(record.chosen_by === "owner" ? text.chosenByYou : text.chosenByAgent);
  if (record.mode === "automatic" && summary.allowed.length)
    lines.push(
      `${text.allowed}: ${summary.allowed.map((item) => modelName(item) ?? "").join(" · ")}`,
    );
  lines.push(usageLine(summary.usage, summary.usage.days, locale));
  return lines;
}

export type ModelCardButton = { key: "confirm" | "cancel"; label: string; primary: boolean };
export type ModelCardSpec = {
  title: string;
  lines: string[];
  hint: string | null;
  buttons: ModelCardButton[];
  outcome: string | null;
};

function stateLine(
  state: OwnerActionModelState | undefined,
  defaultModel: ModelLabel,
  locale: string,
): string {
  return state ? modelChoiceLine(state, defaultModel, locale) : "";
}

/** A model card in the conversation: "Change its model?" or the Undo after a switch. */
export function modelCard(card: OwnerAction, locale: string): ModelCardSpec {
  const lang = language(locale);
  const text = agentModelLabels[lang];
  const facts = card.facts.model;
  const agent = facts?.agent_name ? isolate(facts.agent_name) : text.thisAgent;
  const defaultModel = facts?.default_model ?? { provider: null, model: null, name: null };
  const lines: string[] = [];
  let title: string;
  let hint: string | null = text.unchanged;
  let buttons: ModelCardButton[];
  if (card.kind === "agent_model") {
    title = fill(text.requestTitle, { agent });
    const requested = facts?.requested;
    if (facts?.current)
      lines.push(`${text.now}: ${stateLine(facts.current, defaultModel, locale)}`);
    if (requested) {
      const keep = requested.mode === "fixed" ? text.keptUntil : text.mayChangeAgain;
      lines.push(`${text.requested}: ${stateLine(requested, defaultModel, locale)} · ${keep}`);
      const name = modelName(requested.model);
      if (facts?.allow && name) lines.push(fill(text.joinsList, { model: name }));
    }
    if (facts?.asked_by_agent_name)
      lines.push(fill(text.askedBy, { agent: isolate(facts.asked_by_agent_name) }));
    buttons = [
      {
        key: "confirm",
        label: requested?.model.model ? text.useIt : text.letLonora,
        primary: true,
      },
      { key: "cancel", label: text.notNow, primary: false },
    ];
  } else {
    title = fill(text.switchedTitle, { agent });
    // The arrow points along the reading direction: right to left in Arabic.
    lines.push(
      `${stateLine(facts?.previous, defaultModel, locale)} ${lang === "ar" ? "←" : "→"} ${stateLine(facts?.current, defaultModel, locale)}`,
    );
    buttons = [
      { key: "confirm", label: text.undo, primary: false },
      { key: "cancel", label: text.keep, primary: true },
    ];
  }
  const pending = card.status === "pending";
  let outcome: string | null = null;
  if (!pending) {
    hint = null;
    if (card.status === "confirmed") {
      outcome =
        card.kind === "agent_model_changed"
          ? text.undone
          : fill(text.done, {
              agent,
              model: modelName(facts?.requested?.model) ?? text.defaultModel,
            });
    } else if (card.status === "cancelled") {
      outcome = card.kind === "agent_model_changed" ? text.kept : text.dismissed;
    } else {
      outcome =
        card.status_reason === "model_already_set"
          ? text.alreadySet
          : card.status_reason === "owner_changed_model"
            ? text.ownerChanged
            : card.status_reason === "model_changed_again"
              ? text.changedAgain
              : card.status === "expired"
                ? text.expired
                : text.noLongerApplies;
    }
  }
  return { title, lines, hint, buttons: pending ? buttons : [], outcome };
}
