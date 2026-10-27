/** Reserve connection capacity for writes and the live reply stream on HTTP/1.
 * Reads wait locally; mutations never enter this queue. No request is retried,
 * timed, cancelled or interpreted by this scheduler.
 */
export class ReadRequestGate {
  private active = 0;
  private waiting: Array<() => void> = [];
  constructor(private readonly limit = 3) {}

  private take(): () => void {
    this.active += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.active -= 1;
      this.waiting.shift()?.();
    };
  }

  enter(signal: AbortSignal): (() => void) | Promise<() => void> {
    if (!signal.aborted && this.active < this.limit) return this.take();
    return new Promise((resolve, reject) => {
      const cancelled = () => {
        this.waiting = this.waiting.filter((item) => item !== admit);
        signal.removeEventListener("abort", cancelled);
        const error = new Error("request_cancelled");
        error.name = "AbortError";
        reject(error);
      };
      const admit = () => {
        signal.removeEventListener("abort", cancelled);
        if (signal.aborted) return cancelled();
        resolve(this.take());
      };
      if (signal.aborted) return cancelled();
      this.waiting.push(admit);
      signal.addEventListener("abort", cancelled, { once: true });
    });
  }
}
