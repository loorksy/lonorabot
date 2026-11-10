import type { Routine } from "@lonora/contracts";

/** The cut counts code points, so an emoji is never split. */
const cut = (text: string) => Array.from(text).slice(0, 160).join("");

/** The title a save sends: a new routine is named after its task text, and so is one whose
    text the owner edits while it has no title of its own. A title copied from the task text
    (as both apps create it) is not its own, so it follows the new text. A title set apart
    from the text (by the owner or an agent) is kept. */
export function titleInput(routine: Routine | null, text: string): { title?: string } {
  if (!routine) return { title: cut(text) };
  const stored = routine.prompt.trim();
  if (text.trim() === stored) return {};
  const own = !!routine.title && routine.title.trim() !== cut(stored);
  return own ? {} : { title: cut(text) };
}
