const test = require("node:test");
const assert = require("node:assert/strict");
const vercelConfig = require("../vercel.json");

test("Vercel leaves dashboard routes with FastAPI", () => {
  assert.deepEqual(vercelConfig.rewrites, [
    { source: "/events", destination: "/api/events" },
  ]);
});

test("Vercel demo exposes one complete source-linked run", async () => {
  const { GET, demoEvents } = await import("../api/events.mjs");
  const first = demoEvents[0];
  const last = demoEvents.at(-1);

  assert.equal(first.type, "run_started");
  assert.equal(first.metadata.demo, true);
  assert.equal(last.type, "run_completed");
  assert.equal(last.metadata.status, "succeeded");
  assert.deepEqual(
    demoEvents.map((event) => event.sequence),
    demoEvents.map((_, index) => index + 1),
  );
  assert.equal(new Set(demoEvents.map((event) => event.event_id)).size, demoEvents.length);
  assert.ok(demoEvents.some((event) => event.type === "error"));
  assert.ok(demoEvents.some((event) => event.type === "retrying"));
  assert.ok(
    demoEvents.some((event) => event.tool?.sources?.some((source) => source.url)),
  );

  const response = GET();
  const body = await response.text();
  assert.match(response.headers.get("content-type"), /^text\/event-stream/);
  assert.match(body, /event: run_started/);
  assert.match(body, /event: run_completed/);
});
