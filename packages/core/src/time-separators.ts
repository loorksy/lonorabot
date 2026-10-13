/** Local calendar boundaries and quiet gaps separate persistent chat history. */
function localDay(date: Date): number {
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86_400_000;
}

export function needsTimeSeparator(current: string | Date, previous?: string | Date): boolean {
  const next = new Date(current);
  if (!Number.isFinite(next.getTime())) return false;
  if (!previous) return true;
  const prior = new Date(previous);
  return (
    Number.isFinite(prior.getTime()) &&
    (localDay(next) !== localDay(prior) || next.getTime() - prior.getTime() >= 900_000)
  );
}

export function formatTimeSeparator(
  createdAt: string | Date,
  locale: string,
  labels: { today: string; yesterday: string },
  now = new Date(),
): string {
  const date = new Date(createdAt);
  if (!Number.isFinite(date.getTime())) return "";
  const format = (options: Intl.DateTimeFormatOptions): string => {
    try {
      return new Intl.DateTimeFormat(locale, options).format(date);
    } catch {
      return new Intl.DateTimeFormat(undefined, options).format(date);
    }
  };
  const age = localDay(now) - localDay(date);
  const time = format({ hour: "numeric", minute: "2-digit" });
  if (age === 0) return `${labels.today} ${time}`;
  if (age === 1) return `${labels.yesterday} ${time}`;
  if (age >= 2 && age <= 6) return `${format({ weekday: "long" })} ${time}`;
  return `${format({ month: "short", day: "numeric", ...(date.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}) })} ${time}`;
}

export function timeSeparatorIds<T extends { id: string; createdAt?: string }>(
  messages: readonly T[],
): Set<string> {
  const ids = new Set<string>();
  let previous: string | undefined;
  for (const message of messages) {
    if (!message.createdAt || !Number.isFinite(new Date(message.createdAt).getTime())) continue;
    if (needsTimeSeparator(message.createdAt, previous)) ids.add(message.id);
    previous = message.createdAt;
  }
  return ids;
}
