# Gmail call wrapper

`scripts/gmail-wrapper.cjs` is a small, dependency-free wrapper around the connected Codex Gmail tools. It exposes `search`, `read`, and `batchRead` (one to five IDs). It cannot send, draft, label, or delete mail. Use it only for an authorized task.

Calls are sequential, with at least two seconds after each completed request. Only explicit rate-limit failures are retried: at most two retries, using an exposed `Retry-After` header (seconds or HTTP date), otherwise 30 seconds then 60 seconds. Authentication, ordinary permission errors, and unrelated failures pass through without retry. Successful empty results are not errors. Failed MCP results remain failed MCP results; thrown errors remain thrown errors.

## Load in Codex

The connector lives in Codex, not in the local Python process. A Python CLI cannot intercept it. In Codex's JavaScript tool-execution environment (`functions.exec`), load this trusted repository module and pass the connected `tools` object:

```javascript
const source = await tools.exec_command({
  cmd: "sed -n '1,240p' scripts/gmail-wrapper.cjs",
  workdir: "/absolute/path/to/cv_job",
  max_output_tokens: 6000,
});
if (source.exit_code !== 0) throw new Error('Cannot load Gmail wrapper');
const module = { exports: {} };
new Function('module', source.output)(module);
const timing = load('cv-job.gmail.timing') ?? { nextCall: 0 };
const gmail = module.exports(tools, { timing });
try {
  const result = await gmail.search({
    query: 'to:candidate@example.test newer_than:1d subject:verification',
    max_results: 20,
  });
  // Print identifiers/status only, not raw content or error messages.
  text({
    failed: result?.isError === true,
    messageIds: result?.isError === true ? [] : result?.structuredContent?.message_ids ?? [],
  });
} catch {
  text({ failed: true, action: 'Stop and report incomplete email access; do not print the raw error.' });
} finally {
  store('cv-job.gmail.timing', timing);
}
```

Replace the repository path and query with the selected workspace's active verification flow. Inspect failures before interpreting an empty result. Subsequent executions use the same loading block, timing key, and `finally` block. For reads, replace the search and output with:

```javascript
const result = await gmail.read({ message_id: 'ID_FROM_SEARCH', format: 'full' });
// Use the message only transiently inside this execution. Do not text(result),
// text(result.structuredContent), print snippets, or store the message body.
text({ readSucceeded: result?.isError !== true });
```

Reading successfully does not establish which code is valid. Check recipient/time/tenant/event as described in the accounts guide, then use a supported secure entry path into the active browser flow without returning the secret in output. If the environment cannot do that, ask the user to retrieve/enter the code manually. The wrapper passes connector results through unchanged; it does not redact them for you. Do not print raw thrown errors either. Keep only `nextCall` in timing state, never codes, tokens, queries, or email bodies. `batchRead` requires the same precautions.

This is a call boundary, not a security sandbox: raw connector tools still exist. Agent instructions require routing calls through it. Timing is session-local, not a cross-process mailbox lock; do not run simultaneous email workflows in other chats. Do not recreate state or immediately start a new operation to bypass exhausted retries. If the Codex runtime lacks these execution tools, report that limitation instead of silently making unwrapped calls. Live search/read has been checked in Codex; rate-limit behavior is tested with fake responses, not a forced live quota failure. End-to-end ATS verification is not covered by those tests.

For ordinary Node adapters, use `require('./scripts/gmail-wrapper.cjs')(tools)` and retain the instance. Test without connecting Gmail:

```bash
node --test tests/gmail-wrapper.test.cjs
```

The included `skills/apply-to-jobs/references/accounts.md` guide covers recipient/time/tenant matching, signup versus submission verification, and browser confirmation. Account verification alone does not mean an application was submitted.
