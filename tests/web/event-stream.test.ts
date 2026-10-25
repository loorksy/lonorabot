import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { eventStream } from "../../apps/web/src/lib/events";

class FakeEventSource extends EventTarget {
  static OPEN = 1;
  static instances: FakeEventSource[] = [];
  readyState = 0;
  closed = false;
  onmessage: ((message: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(
    readonly url: string,
    readonly options: EventSourceInit,
  ) {
    super();
    FakeEventSource.instances.push(this);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  ready(cursor: unknown) {
    this.readyState = 1;
    this.dispatchEvent(new MessageEvent("ready", { data: JSON.stringify({ cursor }) }));
  }
  message(value: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(value) }));
  }
}
const originalSource = globalThis.EventSource;
const originalWindow = globalThis.window;
const originalDocument = globalThis.document;
let connection: ReturnType<typeof eventStream> | undefined;

beforeEach(() => {
  mock.timers.enable({ apis: ["setTimeout"] });
  FakeEventSource.instances = [];
  Object.assign(globalThis, {
    EventSource: FakeEventSource,
    window: new EventTarget(),
    document: Object.assign(new EventTarget(), { visibilityState: "visible" }),
  });
});
afterEach(() => {
  connection?.close();
  connection = undefined;
  mock.timers.reset();
  Object.assign(globalThis, {
    EventSource: originalSource,
    window: originalWindow,
    document: originalDocument,
  });
});
const event = (cursor: number) => ({ cursor, kind: "message.created", payload: { id: "saved" } });

test("new live subscription establishes baseline before connected canonical refresh", () => {
  const states: boolean[] = [];
  const seen: number[] = [];
  connection = eventStream(
    0,
    (value) => seen.push(value.cursor),
    (value) => states.push(value),
  );
  const source = FakeEventSource.instances[0];
  assert.equal(source.url, "/api/events/stream?cursor=0&live=true");
  assert.deepEqual(source.options, { withCredentials: true });
  assert.deepEqual(states, []);
  source.message(event(9));
  assert.deepEqual(seen, []);
  source.ready(100_000);
  assert.deepEqual(states, [true]);
  source.message(event(100_001));
  assert.deepEqual(seen, [100_001]);
});

test("empty-owner baseline zero is initialized and reconnect does not skip new events", () => {
  connection = eventStream(
    0,
    () => {},
    () => {},
  );
  const source = FakeEventSource.instances[0];
  source.ready(0);
  source.onerror?.();
  mock.timers.tick(500);
  assert.equal(FakeEventSource.instances[1].url, "/api/events/stream?cursor=0");
});

test("retry resumes exact accepted cursor and ignores malformed, duplicate and stale frames", () => {
  const seen: number[] = [];
  connection = eventStream(
    42,
    (value) => seen.push(value.cursor),
    () => {},
  );
  const first = FakeEventSource.instances[0];
  first.ready(42);
  first.message({ cursor: 90, kind: "bad", payload: null });
  first.message({ cursor: true, kind: "bad", payload: {} });
  first.onmessage?.(new MessageEvent("message", { data: "not json" }));
  first.message(event(43));
  first.message(event(43));
  first.onerror?.();
  assert.equal(first.closed, true);
  assert.equal(FakeEventSource.instances.length, 1);
  mock.timers.tick(500);
  const second = FakeEventSource.instances[1];
  assert.equal(second.url, "/api/events/stream?cursor=43");
  first.message(event(44));
  second.ready(43);
  second.message(event(44));
  assert.deepEqual(seen, [43, 44]);
});

test("logout cancels stream and retries, and stale callbacks cannot cross owner boundary", () => {
  const seen: number[] = [];
  const states: boolean[] = [];
  connection = eventStream(
    2,
    (value) => seen.push(value.cursor),
    (value) => states.push(value),
  );
  const source = FakeEventSource.instances[0];
  source.ready(2);
  source.onerror?.();
  window.dispatchEvent(new Event("lonora:session-reset"));
  mock.timers.tick(20_000);
  source.message(event(3));
  window.dispatchEvent(new Event("online"));
  assert.deepEqual(seen, []);
  assert.equal(FakeEventSource.instances.length, 1);
  assert.equal(states.at(-1), false);
});

test("returning online reconnects promptly without waiting for capped backoff", () => {
  connection = eventStream(
    1,
    () => {},
    () => {},
  );
  const source = FakeEventSource.instances[0];
  source.onerror?.();
  window.dispatchEvent(new Event("online"));
  assert.equal(FakeEventSource.instances.length, 2);
  mock.timers.tick(500);
  assert.equal(FakeEventSource.instances.length, 2);
});

test("silent or proxy-buffered startup retries with cursor preserved", () => {
  connection = eventStream(
    12,
    () => {},
    () => {},
  );
  mock.timers.tick(10_000);
  assert.equal(FakeEventSource.instances[0].closed, true);
  mock.timers.tick(500);
  assert.equal(FakeEventSource.instances[1].url, "/api/events/stream?cursor=12");
});
