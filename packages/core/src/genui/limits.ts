/** Output bounds (review S1), equal in Python: no intermediate text over MAX_TEXT code
 * points and no list over MAX_ITEMS items, so no expression can expand. */
export const MAX_TEXT = 2000;
export const MAX_ITEMS = 201;

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
