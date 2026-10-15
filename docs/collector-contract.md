# Collector protocol (version 1)

This is the shared boundary between the QML UI and Python collector.

```text
python3 /absolute/plugin/scripts/peek.py SECTION --options JSON
```

`SECTION` is one of `docker`, `services`, `processes`, `worktrees`, `disk`.
`JSON` is an object derived from the widget's inline shell settings. Supported
keys: `repositoryRoots` (array of paths), `diskPaths` (array of paths),
`discoveryDepth` (integer 0..5, default 3). Paths may start with `~`; the collector
expands them without shell evaluation. Omitted settings use portable defaults:
repository roots `~/Documents`, `~/Projects`, `~/Work`; disk paths `~`, `~/.cache`,
`~/.local/share`, `~/.npm`. An explicit empty array means no paths configured.
The collector reports effective paths and discovery limits in its notes.
Do not include user-specific paths in versioned settings or tests.

The process emits one UTF-8 JSON document on stdout and exits. Operational
failures are JSON results too; exit 0 means a protocol response was produced,
not that collection succeeded. Invalid usage may exit nonzero. Diagnostics must
not include command environments, secrets or full process arguments.

```json
{
  "schemaVersion": 1,
  "section": "docker",
  "collectedAt": "2026-10-15T12:00:00Z",
  "status": "ok",
  "summary": "12 containers",
  "tables": [{
    "id": "containers",
    "title": "Containers",
    "columns": [{"key": "name", "label": "Name"}, {"key": "state", "label": "State"}],
    "rows": [{"name": "sample", "state": "exited"}]
  }],
  "notes": []
}
```

`status` is `ok`, `partial`, or `error`. All displayed cell values are strings.
`notes` is a list of factual messages, including errors, skipped paths, access
limits, and explicit truncation. Table IDs and columns are section-defined; the
UI presents section summaries and resource lists, with raw tables and diagnostics
available on demand. A table may include `status: "ok" | "partial" | "error"` to
identify its own coverage; an absent status falls back conservatively to the
snapshot status. Failed collection must never be summarized as a confirmed zero.
Never render returned strings as rich text. The UI may filter rows locally.
Rows must not contain synthetic cleanup suggestions or abandonment judgments.
Missing tools/access must be distinguishable from a successful empty result.

## Lifecycle

Collection begins only when a visible section is selected/opened or refreshed.
The Overview view sequences Docker, services and worktrees on demand, presenting
results incrementally with their individual collection times. It never starts
process/disk queries implicitly. Closing or selecting a detail section cancels the
sequence and active request. It does not periodically refresh retained snapshots.
Switching sections cancels the previous active request. Reopening refreshes the
selected section. Each UI instance owns at most one active collector; retained
snapshots are memory-only. Ignore stale completions from cancelled requests.
Closing/destroying the popup terminates collection and all helper subprocesses.
The helper handles SIGTERM/SIGINT and enforces deadlines for child commands.
No subprocesses or timers perform collection while the popup is closed.

## Collector contents

- Docker: use the existing Docker context; report its identity. Containers with
  state/ports/Compose project labels, images, volumes, and `docker system df`.
  Do not start Docker or inspect container environments. Explain that Docker
  reports estimates and that shared layers are not additive.
- Services: system and user service active/substate plus unit-file enablement,
  with timers in a separate table. Reading must not start or enable any unit.
- Processes: readable `/proc` process names, PID, RSS and cwd; listening TCP/UDP
  sockets from `ss`. Do not read environ or cmdline. Report access limits.
- Worktrees: discover repositories under configured roots to the bounded depth,
  prune dependency/cache/build directories, deduplicate real paths/common dirs,
  and query `git worktree list --porcelain -z`. Accept a root that is itself a
  repository. Resolve configured root symlinks and directory aliases safely,
  avoid cycles, and avoid descending into linked worktrees as duplicate repos.
  Show registered path, branch/detached state, working-tree changes and measured
  allocated size; complete/partial/unavailable distinguishes a measured value,
  a lower bound and no observation. Never emit numeric zero for an unstarted scan; missing/locked worktrees remain factual rows. Use
  `GIT_OPTIONAL_LOCKS=0`; no fetch, prune, checkout or index writes. Bound expensive
  discovery, status and size operations; report incomplete results explicitly.
- Disk: configured path totals and immediate children of the first existing
  configured directory, measured allocated bytes with bounded work. Display
  exact measurement caveats: Btrfs reflinks/compression, hardlinks, overlapping
  totals and snapshots prevent interpreting these numbers as reclaimable space.

Read-only portable unit tests cover parsing, missing tools, inaccessible paths,
timeouts, cancellation and path names containing spaces/unicode. A fake backend
may be used for UI tests, but release validation must also invoke real collectors.

## Size presentation

Display allocated bytes in readable binary units. A partial measured size is a
lower bound (`≥`), not an exact total. An unavailable size is “Not measured”.
Do not sum independently measured worktrees, configured paths or process RSS into
an asserted unique-resource total. Docker usage categories remain separately
labeled. Optional bounded GNU `du` measurement can provide complete sizes while
Python's bounded fallback remains available; an unavailable inode count does not
invalidate a complete byte measurement.
