// The owner opened the app (VISION 11.1: the brief time is learned from it). One report per
// owner day is enough: the server keeps only the first open of each owner day.

export type AppOpenPost = (body: { timezone: string }) => Promise<unknown>;

// The owner's day starts at 04:00 on the device's clock, as on the server
// (lonora_db.app_opens.DAY_START_HOUR): an open at 00:30 belongs to the day before.
export const OWNER_DAY_START_HOUR = 4;

/** The owner day (YYYY-MM-DD) of a moment on the device's clock in this zone: its date, or
 *  the date before until 04:00, the day the server files an open under. */
export function ownerDay(at: Date, timeZone: string): string {
  const date = at.toLocaleDateString("en-CA", { timeZone });
  const hour = Number(
    at.toLocaleTimeString("en-GB", { timeZone, hour: "2-digit", hourCycle: "h23" }),
  );
  if (hour >= OWNER_DAY_START_HOUR) return date;
  const [year, month, day] = date.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day - 1)).toISOString().slice(0, 10);
}

/** A reporter to call whenever the app comes to the front; it posts at most once per
 *  owner day, and again on the same day only after a failed post. */
export function appOpenReporter(post: AppOpenPost, now: () => Date = () => new Date()) {
  let reported: string | null = null;
  return (): void => {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!timezone) return;
    const date = ownerDay(now(), timezone);
    if (reported === date) return;
    reported = date;
    void post({ timezone }).catch(() => {
      if (reported === date) reported = null;
    });
  };
}
