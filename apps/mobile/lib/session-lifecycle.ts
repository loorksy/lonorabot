const teardowns = new Set<() => Promise<void>>();
export function registerSessionTeardown(callback: () => Promise<void>) {
  teardowns.add(callback);
  return () => {
    teardowns.delete(callback);
  };
}
export async function closeSessionResources() {
  await Promise.all([...teardowns].map((close) => close()));
}
