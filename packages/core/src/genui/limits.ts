/** Output bounds (review S1), equal in Python: no intermediate text over MAX_TEXT code
 * points and no list over MAX_ITEMS items, so no expression can expand. */
export const MAX_TEXT = 2000;
export const MAX_ITEMS = 201;
/** One budget for a whole value however it nests (review round 4): a text costs its code
 * points, every other value 1, a list or object 1 plus its contents. */
export const MAX_SIZE = 20000;

/** Code points, as Python's `len` counts them. */
export function textSize(text: string): number {
  let size = 0;
  for (let index = 0; index < text.length; index += 1) {
    const unit = text.charCodeAt(index);
    if (unit < 0xdc00 || unit > 0xdfff || index === 0) size += 1;
    else {
      const previous = text.charCodeAt(index - 1);
      if (previous < 0xd800 || previous > 0xdbff) size += 1;
    }
  }
  return size;
}

/** Whether a value costs more than `limit`; stops as soon as it does. */
export function overBudget(value: unknown, limit = MAX_SIZE): boolean {
  let total = 0;
  const stack: unknown[] = [value];
  while (stack.length) {
    const item = stack.pop();
    if (typeof item === "string") total += textSize(item);
    else if (Array.isArray(item)) {
      if (item.length > MAX_ITEMS) return true;
      total += 1;
      stack.push(...item);
    } else if (item !== null && typeof item === "object") {
      total += 1;
      stack.push(...Object.values(item as Record<string, unknown>));
    } else total += 1;
    if (total > limit) return true;
  }
  return false;
}
