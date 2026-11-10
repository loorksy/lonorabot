import type { Routine } from "@lonora/contracts";

/** The title a save sends: a new routine is named after its task text, and so is one with no
    title of its own whose text the owner edits. A title already set (by the owner or an agent)
    is kept. The cut counts code points, so an emoji is never split. */
export function titleInput(routine: Routine | null, text: string): { title?: string } {
  if (routine && (routine.title || text === routine.prompt)) return {};
  return { title: Array.from(text).slice(0, 160).join("") };
}
