/** Download only. Activation belongs to the next native launch, never to a live conversation. */
export function createUpdateChecker(
  adapter: {
    check: () => Promise<{ isAvailable: boolean; isRollBackToEmbedded?: boolean }>;
    fetch: () => Promise<unknown>;
  },
  options: { now?: () => number; onFailure?: () => void; interval?: number } = {},
) {
  const now = options.now ?? Date.now;
  const interval = options.interval ?? 10 * 60 * 1000;
  let attempted: number | undefined;
  let pending = false;
  let stopped = false;
  return {
    async check() {
      const time = now();
      if (stopped || pending || (attempted !== undefined && time - attempted < interval)) return;
      pending = true;
      attempted = time;
      try {
        const result = await adapter.check();
        if ((result.isAvailable || result.isRollBackToEmbedded) && !stopped) await adapter.fetch();
      } catch {
        options.onFailure?.();
      } finally {
        pending = false;
      }
    },
    stop() {
      stopped = true;
    },
  };
}
