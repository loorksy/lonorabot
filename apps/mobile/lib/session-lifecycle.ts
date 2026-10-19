const teardowns = new Set<() => Promise<void>>();
export function registerSessionTeardown(callback: () => Promise<void>) {
  teardowns.add(callback);
  return () => {
    teardowns.delete(callback);
  };
}
export async function closeSessionResources() {
  const results = await Promise.allSettled(
    [...teardowns].map((close) => Promise.resolve().then(close)),
  );
  const failure = results.find((result) => result.status === "rejected");
  if (failure?.status === "rejected") throw failure.reason;
}
