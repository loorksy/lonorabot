/** OpenUI-inspired scroll affordance hysteresis; no message/runtime state lives here.
 * MIT, Thesys Inc., revision9d73d17. See THIRD_PARTY_NOTICES.md.
 */
export function showLatestButton(wasVisible: boolean, distanceToEnd: number): boolean {
  return wasVisible ? distanceToEnd > 24 : distanceToEnd > 96;
}

/** Keep the latest message in view until the owner moves up.

 * A stream render can run before the scroll event. A position already above
 * the last anchored bottom releases follow, so that render does not pull the
 * transcript back down over an older page the owner just opened. The first
 * pin (anchored at 0) still opens the thread on the latest message. */
export function stickToLatest(
  position: { scrollHeight: number; scrollTop: number },
  following: { current: boolean },
  anchored: { current: number },
  nearBottom: boolean,
): void {
  if (anchored.current > 0 && position.scrollTop + 1 < anchored.current && !nearBottom)
    following.current = false;
  if (!following.current) return;
  position.scrollTop = position.scrollHeight;
  anchored.current = position.scrollTop;
}
