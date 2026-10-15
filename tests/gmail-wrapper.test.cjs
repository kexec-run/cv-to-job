const { test } = require('node:test');
const assert = require('node:assert/strict');
const createGmail = require('../scripts/gmail-wrapper.cjs');

function setup(responses) {
  let time = 0;
  let active = 0;
  let maxActive = 0;
  const calls = [];
  const timing = { nextCall: 0 };
  const tool = async args => {
    active++;
    maxActive = Math.max(active, maxActive);
    calls.push({ args, time });
    await Promise.resolve();
    active--;
    const response = responses.shift();
    if (response instanceof Error) throw response;
    return response;
  };
  const tools = Object.fromEntries(['search_email_ids', 'read_email', 'batch_read_email']
    .map(name => [`mcp__codex_apps__gmail_${name}`, tool]));
  const options = { now: () => time, sleep: async ms => { time += ms; }, timing };
  return { gmail: createGmail(tools, options), calls, timing, tools, options, maxActive: () => maxActive };
}

test('serializes calls, spaces requests, and exposes only reads', async () => {
  const fixture = setup([{ ids: [] }, { id: 'one' }, { messages: [] }]);
  const results = await Promise.all([
    fixture.gmail.search({ query: 'to:candidate@example.test' }),
    fixture.gmail.read({ message_id: 'one' }),
    fixture.gmail.batchRead({ message_ids: ['one'] }),
  ]);
  assert.deepEqual(results[0], { ids: [] });
  assert.deepEqual(fixture.calls.map(call => call.time), [0, 2000, 4000]);
  assert.equal(fixture.maxActive(), 1);
  assert.deepEqual(Object.keys(fixture.gmail), ['search', 'read', 'batchRead']);
});

test('retries explicit MCP rate errors twice, returning the original final error', async () => {
  const limited = { isError: true, content: [{ type: 'text', text: 'rate limit exceeded' }] };
  const fixture = setup([limited, limited, limited]);
  assert.equal(await fixture.gmail.search({}), limited);
  assert.deepEqual(fixture.calls.map(call => call.time), [0, 30000, 90000]);
  assert.equal(fixture.timing.nextCall, 150000);
});

test('retries thrown 429 errors and honors Retry-After', async () => {
  const error = Object.assign(new Error('limited'), { status: 429, headers: { 'Retry-After': '45' } });
  const fixture = setup([error, { ids: [] }]);
  await fixture.gmail.search({});
  assert.deepEqual(fixture.calls.map(call => call.time), [0, 45000]);
});

test('accepts HTTP dates and uses fallback for invalid Retry-After', async () => {
  const fixture = setup([
    Object.assign(new Error('limited'), { status: 429, headers: { 'retry-after': new Date(40000).toUTCString() } }),
    Object.assign(new Error('limited'), { status: 429, headers: { 'retry-after': 'nonsense' } }),
    {},
  ]);
  await fixture.gmail.search({});
  assert.deepEqual(fixture.calls.map(call => call.time), [0, 40000, 100000]);
});

test('does not retry authentication, permission, or generic failures', async () => {
  for (const status of [401, 403, 500]) {
    const error = Object.assign(new Error('request failed'), { status });
    const fixture = setup([error]);
    await assert.rejects(fixture.gmail.search({}), value => value === error);
    assert.equal(fixture.calls.length, 1);
  }
});

test('explicit quota reason on a 403 is retryable', async () => {
  const fixture = setup([Object.assign(new Error('userRateLimitExceeded'), { status: 403 }), {}]);
  await fixture.gmail.search({});
  assert.equal(fixture.calls.length, 2);
});

test('successful email text containing rate-limit words is never retried', async () => {
  const result = { content: [{ type: 'text', text: 'Your quotaExceeded report' }] };
  const fixture = setup([result]);
  assert.equal(await fixture.gmail.read({ message_id: 'one' }), result);
  assert.equal(fixture.calls.length, 1);
});

test('a rejected call does not poison the queue', async () => {
  const fixture = setup([new Error('offline'), {}]);
  await assert.rejects(fixture.gmail.search({}), /offline/);
  await fixture.gmail.search({});
  assert.equal(fixture.calls.length, 2);
});

test('passes through structured errors and honors structured Retry-After', async () => {
  const result = { isError: true, structuredContent: { error: { status: 429, headers: { 'retry-after': '3' } } } };
  const fixture = setup([result, {}]);
  await fixture.gmail.search({});
  assert.deepEqual(fixture.calls.map(call => call.time), [0, 3000]);
  const failure = { isError: true, content: [{ type: 'text', text: 'unauthorized' }] };
  const other = setup([failure]);
  assert.equal(await other.gmail.search({}), failure);
  assert.equal(other.calls.length, 1);
});

test('shared timing survives wrapper recreation without persisting email data', async () => {
  const fixture = setup([{}, {}]);
  await fixture.gmail.search({ query: 'private query' });
  await createGmail(fixture.tools, fixture.options).search({});
  assert.deepEqual(fixture.calls.map(call => call.time), [0, 2000]);
  assert.deepEqual(Object.keys(fixture.timing), ['nextCall']);
});

test('refuses oversized batches and missing connector methods without a call', async () => {
  const fixture = setup([]);
  await assert.rejects(fixture.gmail.batchRead({ message_ids: [] }), /one to five/);
  await assert.rejects(fixture.gmail.batchRead({ message_ids: Array(6).fill('id') }), /one to five/);
  assert.equal(fixture.calls.length, 0);
  await assert.rejects(createGmail({}).search({}), /connector unavailable/);
});
