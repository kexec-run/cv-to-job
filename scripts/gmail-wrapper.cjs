// One instance per mailbox/session. The caller supplies Codex's connected tools.
module.exports = function createGmail(tools, {
  sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
  now = Date.now,
  timing = { nextCall: 0 },
} = {}) {
  let queue = Promise.resolve();

  function details(value) {
    return value?.structuredContent?.error ?? value?.error ?? value?.structuredContent ?? value;
  }

  function isRateLimit(value) {
    const error = details(value);
    const status = error?.status ?? error?.statusCode ?? error?.code;
    // Authentication/permission failures must not be retried as quota failures.
    if (Number(status) === 401) return false;
    if (Number(status) === 429) return true;
    const message = error?.message ?? value?.message ?? value?.content
      ?.filter(item => item.type === 'text').map(item => item.text).join('\n') ?? '';
    return /rate[ _-]?limit(?:ed|exceeded)?|userRateLimitExceeded|quotaExceeded|too many requests/i.test(message);
  }

  function retryDelay(value, fallback) {
    const error = details(value);
    const headers = error?.headers ?? value?.headers;
    const raw = headers?.get?.('retry-after') ?? headers?.['retry-after'] ?? headers?.['Retry-After'];
    if (raw === undefined || raw === null || String(raw).trim() === '') return fallback;
    const seconds = Number(raw);
    const delay = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(raw) - now();
    return Number.isFinite(delay) && delay >= 0 ? delay : fallback;
  }

  async function call(name, args) {
    const tool = tools[name];
    if (typeof tool !== 'function') throw new Error(`Gmail connector unavailable: ${name}`);
    for (let attempt = 0; ; attempt++) {
      await sleep(Math.max(0, timing.nextCall - now()));
      let result;
      let thrown = false;
      try {
        result = await tool(args);
      } catch (error) {
        result = error;
        thrown = true;
      }
      timing.nextCall = now() + 2000;
      // Never inspect successful email bodies for error keywords.
      const failed = thrown || result?.isError === true;
      if (!failed || !isRateLimit(result)) {
        if (thrown) throw result;
        return result;
      }
      timing.nextCall = now() + Math.max(2000, retryDelay(result, attempt === 0 ? 30000 : 60000));
      if (attempt === 2) {
        if (thrown) throw result;
        return result;
      }
    }
  }

  function enqueue(name, args) {
    const pending = queue.then(() => call(name, args));
    queue = pending.catch(() => {});
    return pending;
  }

  return Object.freeze({
    search: args => enqueue('mcp__codex_apps__gmail_search_email_ids', args),
    read: args => enqueue('mcp__codex_apps__gmail_read_email', args),
    batchRead: args => {
      if (!Array.isArray(args?.message_ids) || args.message_ids.length < 1 || args.message_ids.length > 5) {
        return Promise.reject(new Error('batchRead requires one to five message IDs'));
      }
      return enqueue('mcp__codex_apps__gmail_batch_read_email', args);
    },
  });
};
