# Multiple agents in one workspace

Use one coordinator and a unique, non-secret owner ID for each worker/session. All agents must use the repository CLI for application records; do not edit `applications.json` directly. Existing records need no migration. Unclaimed records remain usable by the single-agent commands.

## Start one shared run

Only the coordinator starts or ends the run:

```bash
uv run cv-job applications run start --owner run-alpha-coordinator --target 5 --objective "Prepare five applications"
```

Starting another run while one is active is refused; it no longer silently ends the current run. Keep the returned run ID and resume it. An owned run can only be ended with its coordinator's `--owner`. Legacy unowned runs remain readable and can be ended explicitly.

## Claim before preparing or applying

For a new opening, create the record and claim it in the same transaction:

```bash
uv run cv-job applications add --company "Example" --title "Systems Engineer" \
  --url "https://example.test/jobs/123" --owner run-alpha-worker-1
```

Use the returned ID and folder. A separate `check` is informative, not a reservation. Concurrent adds for the same known URL have one winner. After an ATS redirect, link the verified URL to the same record; a URL belonging to another record is refused. Stop and coordinate a handoff on that conflict instead of continuing with two applications. Different URLs cannot be proven to represent the same opening until the employer/requisition/location and URL relationship are checked.

For an existing unfinished record:

```bash
uv run cv-job applications claim --id APPLICATION_ID --owner run-alpha-worker-1
uv run cv-job applications show --id APPLICATION_ID
uv run cv-job applications update --id APPLICATION_ID --owner run-alpha-worker-1 --status review_ready
```

Each successful claim automatically includes the application in the active run, even when it was created in an older run. Repeated claims and release → claim handoffs count it only once. Its original `run` and history stay intact; no active run is required to claim. `status`, `list --run RUN_ID`, `report`, and run-end counts include both original and resumed applications, using their current status rather than a historical snapshot. Older runs without participation data still work; past resumes are not inferred or backfilled.

`show --id APPLICATION_ID` prints the complete record as JSON, including its owner, folder, attachments, details/unresolved answers, and history when present. It is read-only, needs no owner, and fails if the ID is missing. Treat its output as private candidate data.

Use `--owner` on every update to a claimed record, including attachment/details updates and URL linking. Missing or mismatched owners are refused. A worker cannot update an unclaimed record by merely supplying its owner ID; it must claim it first. A claim by the same owner is idempotent. Submitted/rejected records cannot be newly claimed. Owner IDs are cooperative identifiers, not authentication credentials: never share one between simultaneous workers or reuse IDs across unrelated sessions.

Workers use different application folders and browser contexts. Do not rewrite the master, role bases, shared preferences, or submitted artifacts in parallel. Write documents only in the assigned folder, preserving any existing documents. Claims coordinate ownership; renderers and browser tools do not enforce them automatically. Recheck ownership before browser submission and obey saved user/site submission rules—ownership is not permission to submit.

## Release or recover deliberately

After a worker stops using the folder/form and hands back its results:

```bash
uv run cv-job applications release --id APPLICATION_ID --owner run-alpha-worker-1
```

Claims do not expire when a process exits. If a worker crashes or a submission result is ambiguous, stop that worker, check the portal/log/artifacts, and record the verified state before releasing its claim and assigning another owner. The coordinator may use the recorded owner ID for that deliberate recovery. There is no timeout-based claim stealing or force-unlock operation. Do not release a claim while its worker may still be acting in the browser.

The coordinator ends the shared run after workers have stopped and outcomes/handoffs have been reviewed:

```bash
uv run cv-job applications run end --owner run-alpha-coordinator
uv run cv-job applications report
```

## What file locking protects

Every mutating application CLI command takes an exclusive Python `fcntl.flock` on a permanent sidecar beside the resolved configured log: usually `private/applications.json.lock`. The lock covers loading the latest JSON, deduplication/ownership checks, mutation, and save. Configurations referring to the same resolved log share that lock. Readers see the complete old or new JSON without taking a writer lock.

Saving uses a unique sibling temporary file, flushes/fsyncs it, then atomically replaces the JSON. Existing log permissions are preserved. A failed pre-replacement write leaves the old JSON intact; the command removes only its own temporary file, never a pre-existing staging file. Folder creation and JSON are not one filesystem transaction: a failed add can leave an unrecorded folder. Keep it for inspection; later adds choose a different available folder rather than overwriting it.

The lock is held only during the short CLI transaction, never while browsing, rendering, or waiting for email. The default wait is 10 seconds; put `--lock-timeout SECONDS` after the mutating subcommand if needed. Timeout returns exit code `3`; configuration/transaction failures return `2`; ownership/deduplication conflicts return nonzero. A failed command must not be treated as a successful reservation/update. After an ambiguous failure, reread the log before retrying.

Never delete the sidecar to unlock it. Closing the final holder descriptor releases the OS lock, including after process death; the file remaining is normal. All writers must cooperate. Direct JSON edits, separate clones, independently copied workspaces, or synced folders do not gain cross-agent coordination from this lock.

## Browser, email, and platform limits

File locking does not provide exactly-once ATS submission. Use one owner per opening and browser context, then inspect the portal after an uncertain result. Keep Gmail access serialized through one coordinator/session using the wrapper; its queue is not a cross-agent mailbox lock. Do not request extra OTPs to evade a cooldown.

The target is local POSIX filesystems on Linux/macOS and Linux processes inside WSL2 using `/home/...`. Native Windows writes fail closed if `fcntl` is unavailable. WSL1, `/mnt/c` with mixed Windows/WSL writers, network shares, cloud-synced folders, and cross-machine coordination are not promised. A library/API existing is not proof that a particular filesystem behaves correctly.

Linux process-contention tests are run locally and in CI; a macOS CI job runs the same locking tests after pushing. Actual macOS/WSL runtime verification must be reported separately; adding a CI job is not a passing result. To check a WSL2 installation, run from its Linux filesystem:

```bash
uv sync --frozen
uv run pytest -q tests/test_application_locking.py
```

Tests use fictional temporary workspaces. They cover concurrent adds, deduplication, history updates, owner/run conflicts, lock timeout, killed lock holders, path aliases, failed replacement, and artifact/permission preservation. They do not contact an ATS or mailbox.
