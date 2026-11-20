import { test as base } from "@playwright/test";

export { expect } from "@playwright/test";

/* What a test created is undone by the steps it hands to `cleanup(step)`, not in a `finally`.
   The steps run in reverse order in this fixture's teardown: after the test body, also one
   that timed out, and before Playwright closes the context (this fixture depends on it), so
   their requests still reach the server. A step that fails is reported next to the test's own
   error. A `finally` that throws replaces it instead, and after a timeout a request there fails
   at once on the closed context: the report then named the cleanup, not the action that hung. */
export const test = base.extend({
  cleanup: async ({ context: _context }, use) => {
    const steps = [];
    await use((step) => {
      steps.push(step);
    });
    let failure;
    for (const step of steps.reverse()) {
      try {
        await step();
      } catch (error) {
        failure ??= error;
      }
    }
    if (failure) throw failure;
  },
});
