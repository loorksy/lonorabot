// The owner opened the app (VISION 11.1: the brief time is learned from it). One report per
// local date of the device is enough: the server keeps only the first open of each date.

export type AppOpenPost = (body: { timezone: string }) => Promise<unknown>;

/** A reporter to call whenever the app comes to the front; it posts at most once per
 *  local date of the device, and again on the same date only after a failed post. */
export function appOpenReporter(post: AppOpenPost, now: () => Date = () => new Date()) {
  let reported: string | null = null;
  return (): void => {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!timezone) return;
    const date = now().toLocaleDateString("en-CA", { timeZone: timezone });
    if (reported === date) return;
    reported = date;
    void post({ timezone }).catch(() => {
      if (reported === date) reported = null;
    });
  };
}
