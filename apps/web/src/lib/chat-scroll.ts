/** OpenUI-inspired scroll affordance hysteresis; no message/runtime state lives here.
 * MIT, Thesys Inc., revision9d73d17. See THIRD_PARTY_NOTICES.md.
 */
export function showLatestButton(wasVisible: boolean, distanceToEnd: number): boolean {
  return wasVisible ? distanceToEnd > 24 : distanceToEnd > 96;
}
