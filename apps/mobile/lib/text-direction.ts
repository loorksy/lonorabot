import { textDirection as readingDirection } from "@lonora/core";

export type TextDirection = "rtl" | "ltr";

/**
 * The direction text written by an agent or person reads in (core textDirection, as Web):
 * any Arabic letter makes it right-to-left, a text whose letters are all Latin reads
 * left-to-right, and text without a letter (numbers, symbols) follows the interface.
 */
export function textDirection(text: string, fallback: TextDirection): TextDirection {
  return readingDirection(text) ?? fallback;
}
