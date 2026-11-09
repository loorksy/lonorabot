import { plural, t } from "@lingui/core/macro";

/* The reference's Arabic counts (arCount): one, two, 3–10, 11 and more. */
export const chatsWord = (count: number) =>
  plural(count, {
    one: "one chat",
    two: "two chats",
    few: "# chats",
    many: "# chats",
    other: "# chats",
  });
/** A list's size: «فارغة» when it holds nothing. */
export const listSize = (count: number) => (count ? chatsWord(count) : t`Empty`);
