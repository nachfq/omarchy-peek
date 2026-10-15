#!/usr/bin/env python3
"""On-demand, read-only Linux snapshots using collector protocol v1."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import time

SCHEMA_VERSION = 1
COLLECTION_SECONDS = 20
MAX_FILTERS = 64
SECTIONS = ("docker", "services", "processes", "worktrees", "disk")
MAX_OUTPUT = 1024 * 1024
MAX_ROWS = 500
MAX_DISCOVERY = 5000
MAX_SCAN_ENTRIES = 20000
MAX_TOTAL_ENTRIES = 100000
PRUNE = {".git", "node_modules", ".cache", ".venv", "venv", "vendor", "build",
         "dist", "target", "__pycache__", ".npm", ".local", ".Trash"}
SIZE_CAVEAT = ("Sizes are allocated bytes (st_blocks × 512), counted once per inode within "
               "each measurement; symlinks are not followed and other filesystems are skipped. "
               "Btrfs reflinks/compression, hardlinks, overlapping paths and snapshots mean "
               "these values are not reclaimable space. Separate rows must not be added.")


class Cancelled(BaseException):
    """Unwind collectors and their active subprocess groups on UI cancellation."""


class DeadlineReached(BaseException):
    """Stop the whole snapshot; never treat its expired timer as a recoverable tool error."""


class CollectionError(Exception):
    pass


def text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return str(value)


class Snapshot:
    def __init__(self, section):
        self.data = {"schemaVersion": SCHEMA_VERSION, "section": section,
                     "collectedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                     "status": "ok", "summary": "", "tables": [], "notes": []}
        self.failed = False
        self.successes = 0

    def note(self, message, failure=False):
        if message not in self.data["notes"]:
            self.data["notes"].append(message)
        self.failed |= failure

    def table(self, ident, title, columns, rows):
        if len(rows) > MAX_ROWS:
            self.note(f"{title}: truncated to {MAX_ROWS} rows.", True)
        self.data["tables"].append({"id": ident, "title": title,
                                    "columns": [{"key": key, "label": label} for key, label in columns],
                                    "rows": [{key: text(row.get(key, "")) for key, _ in columns}
                                             for row in rows[:MAX_ROWS]]})

    def finish(self, summary):
        self.data["summary"] = summary
        self.data["status"] = ("partial" if self.successes else "error") if self.failed else "ok"
        return self.data


class Budget:
    def __init__(self, seconds=None):
        self.deadline = time.monotonic() + (COLLECTION_SECONDS if seconds is None else seconds)
        self.entries = 0

    def check(self):
        if time.monotonic() >= self.deadline:
            raise DeadlineReached()


def stop_group(process):
    """Signal the entire session even if the direct child has already exited."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.08)
    except subprocess.TimeoutExpired:
        pass
    # A grandchild can retain a pipe after its parent exits or ignore SIGTERM.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_command(args, budget, timeout=3, env=None, max_output=MAX_OUTPUT):
    """Bound combined stdout/stderr without communicate() buffering unlimited data."""
    budget.check()
    deadline = min(budget.deadline, time.monotonic() + timeout)
    process = None
    selector = selectors.DefaultSelector()
    output = bytearray()
    total = 0
    # Avoid a signal between spawning the child and registering it for cleanup.
    signals = {signal.SIGTERM, signal.SIGINT, signal.SIGALRM}
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
    try:
        try:
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True, env=env)
        except FileNotFoundError:
            raise CollectionError(f"{args[0]} is not installed or not on PATH.") from None
        except OSError as exc:
            raise CollectionError(f"{args[0]} could not start ({exc.strerror}).") from None
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map() or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                budget.check()
                raise CollectionError(f"{args[0]} timed out; results are incomplete.")
            for key, _ in selector.select(min(remaining, 0.05)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > max_output:
                    raise CollectionError(f"{args[0]} output exceeded {max_output} bytes; results are incomplete.")
                if key.fileobj is process.stdout:
                    output.extend(chunk)
        if process.returncode:
            # Tool stderr can include credentials, endpoints or full command arguments.
            raise CollectionError(f"{args[0]} exited with status {process.returncode}; tool/access unavailable.")
        return output.decode("utf-8", errors="surrogateescape")
    finally:
        # Ignore repeated cancellation while cleaning up, then restore the caller's mask.
        cleanup_mask = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
        try:
            if process is not None:
                stop_group(process)
                process.stdout.close()
                process.stderr.close()
            selector.close()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, cleanup_mask)


def command(snapshot, budget, args, **kwargs):
    try:
        result = run_command(args, budget, **kwargs)
        snapshot.successes += 1
        return result
    except CollectionError as exc:
        snapshot.note(str(exc), True)
        return None


def json_records(raw):
    """Docker emits one JSON object per line; systemctl emits a JSON array."""
    if raw is None:
        return []
    try:
        if raw.lstrip().startswith("["):
            records = json.loads(raw)
        else:
            records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (ValueError, TypeError):
        raise CollectionError("Tool returned malformed JSON; results are incomplete.") from None
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise CollectionError("Tool returned an unexpected JSON structure.")
    return records


def records(snapshot, raw, label):
    if raw is None:
        snapshot.note(f"{label}: unavailable; command did not return data.", True)
        return []
    try:
        return json_records(raw)
    except CollectionError as exc:
        snapshot.note(f"{label}: {exc}", True)
        return []


def collect_docker(snapshot, options, budget):
    context = command(snapshot, budget, ["docker", "context", "show"])
    if context is not None:
        snapshot.note("Docker context: " + context.strip())
    specs = [
        ("containers", "Containers", ["container", "ls", "--all"],
         [("Names", "Name"), ("State", "State"), ("Status", "Status"), ("Ports", "Ports"),
          ("composeProject", "Compose project")]),
        ("images", "Images", ["image", "ls"],
         [("Repository", "Repository"), ("Tag", "Tag"), ("ID", "ID"), ("Size", "Docker size")]),
        ("volumes", "Volumes", ["volume", "ls"],
         [("Name", "Name"), ("Driver", "Driver"), ("Scope", "Scope")]),
        ("usage", "Docker disk usage", ["system", "df"],
         [("Type", "Resource"), ("TotalCount", "Total"), ("Active", "Active"),
          ("Size", "Docker size"), ("Reclaimable", "Docker reported reclaimable")]),
    ]
    count = 0
    for ident, title, args, columns in specs:
        # Only extract the Compose project label, never container environments.
        fmt = ('{"Names":{{json .Names}},"State":{{json .State}},"Status":{{json .Status}},'
               '"Ports":{{json .Ports}},"composeProject":{{json (.Label "com.docker.compose.project")}}}'
               if ident == "containers" else "{{json .}}")
        raw = command(snapshot, budget, ["docker", *args, "--format", fmt])
        rows = records(snapshot, raw, title)
        snapshot.table(ident, title, columns, rows)
        if ident == "containers":
            count = len(rows)
    snapshot.note("Docker reports size estimates. Shared image layers are not additive; Docker's reclaimable field is tool-reported, not a cleanup recommendation.")
    return snapshot.finish(f"{count} containers")


def timer_time(value):
    # systemctl JSON represents timestamps in microseconds since the Unix epoch.
    if isinstance(value, (int, float)):
        if value == 0 or value >= 2**64 - 1:
            return "n/a"
        try:
            return dt.datetime.fromtimestamp(value / 1_000_000, dt.timezone.utc).isoformat(timespec="seconds")
        except (ValueError, OverflowError, OSError):
            return "n/a"
    return text(value)


def collect_services(snapshot, options, budget):
    services, timers = [], []
    for scope, scope_args in (("system", []), ("user", ["--user"])):
        base = ["systemctl", *scope_args, "--no-pager", "--plain", "--output=json"]
        raw = command(snapshot, budget, [*base, "list-units", "--type=service", "--all"])
        active = records(snapshot, raw, f"{scope} services")
        active_available = raw is not None
        try:
            json_records(raw)
        except CollectionError:
            active_available = False
        raw = command(snapshot, budget, [*base, "list-unit-files", "--type=service"])
        files = records(snapshot, raw, f"{scope} unit files")
        units = {}
        for row in files:
            unit = row.get("unit_file", row.get("unit", ""))
            units[unit] = {"scope": scope, "unit": unit, "enablement": row.get("state", ""),
                           "active": "not loaded" if active_available else "unavailable", "sub": "", "description": ""}
        for row in active:
            unit = row.get("unit", "")
            item = units.setdefault(unit, {"scope": scope, "unit": unit, "enablement": "unavailable"})
            item.update(active=row.get("active", ""), sub=row.get("sub", ""), description=row.get("description", ""))
        services.extend(units[key] for key in sorted(units))
        raw = command(snapshot, budget, [*base, "list-timers", "--all"])
        for row in records(snapshot, raw, f"{scope} timers"):
            timers.append({"scope": scope, "unit": row.get("unit", ""),
                           "activates": row.get("activates", ""), "next": timer_time(row.get("next")),
                           "last": timer_time(row.get("last"))})
    snapshot.table("services", "Services", [("scope", "Scope"), ("unit", "Unit"), ("active", "Active"),
                   ("sub", "Substate"), ("enablement", "Unit-file state"), ("description", "Description")], services)
    snapshot.table("timers", "Timers", [("scope", "Scope"), ("unit", "Timer"), ("activates", "Activates"),
                   ("next", "Next (UTC)"), ("last", "Last (UTC)")], timers)
    snapshot.note("System and user managers are queried separately. Unit-file state is enablement, not activation; 'not loaded' means absent from list-units.")
    return snapshot.finish(f"{len(services)} services; {len(timers)} timers")


def parse_rss(status):
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            fields = line.split()
            if len(fields) != 3 or fields[2] != "kB":
                raise ValueError("Unexpected VmRSS unit")
            return str(int(fields[1]) * 1024)
    return "unavailable"


def parse_sockets(raw):
    rows = []
    for line in raw.splitlines():
        parts = line.split(None, 6)
        if len(parts) < 6:
            raise CollectionError("ss returned an unrecognized socket row.")
        rows.append(dict(zip(("protocol", "state", "receive", "send", "local", "peer", "process"), parts)))
    return rows


def read_limited(path, limit=65536):
    with open(path, "rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise OSError("File exceeded read limit")
    return data.decode("utf-8", errors="replace")


def collect_processes(snapshot, options, budget, proc_root=Path("/proc")):
    processes, unavailable = [], 0
    try:
        # Enumeration is capped before sorting, so even directory listing is bounded.
        pids = []
        with os.scandir(proc_root) as entries:
            for entry in entries:
                budget.check()
                if entry.name.isdecimal():
                    pids.append(entry.name)
                    if len(pids) >= MAX_ROWS:
                        snapshot.note(f"Process discovery limited to {MAX_ROWS} PIDs.", True)
                        break
        for pid in sorted(pids, key=int):
            budget.check()
            base = proc_root / pid
            try:
                name = read_limited(base / "comm", 4096).rstrip("\n")
                rss = parse_rss(read_limited(base / "status"))
            except (OSError, ValueError):
                unavailable += 1
                continue
            try:
                cwd = os.readlink(base / "cwd")
            except OSError:
                cwd = "unavailable"
                unavailable += 1
            processes.append({"pid": pid, "name": name, "rss": rss, "cwd": cwd})
        snapshot.successes += 1
    except (OSError, CollectionError) as exc:
        snapshot.note(f"Process inspection incomplete: {exc}", True)
    if unavailable:
        snapshot.note(f"{unavailable} process fields/entries were inaccessible or disappeared during collection.", True)
    snapshot.table("processes", "Processes", [("pid", "PID"), ("name", "Name"), ("rss", "RSS (bytes)"), ("cwd", "Current directory")], processes)
    raw = command(snapshot, budget, ["ss", "--listening", "--tcp", "--udp", "--numeric", "--no-header", "--processes"])
    sockets = []
    if raw is not None:
        try:
            sockets = parse_sockets(raw)
        except CollectionError as exc:
            snapshot.note(str(exc), True)
    snapshot.table("sockets", "Listening sockets", [("protocol", "Protocol"), ("state", "State"),
                   ("local", "Local endpoint"), ("peer", "Peer endpoint"), ("process", "Process / PID")], sockets)
    snapshot.note("RSS is resident memory, not unique memory. Socket process names/PIDs are shown only where ss has access; empty ownership is not proof of no owner. TCP listeners and UDP bound sockets are included.")
    return snapshot.finish(f"{len(processes)} processes; {len(sockets)} sockets")


def configured_paths(options, key):
    defaults = {"repositoryRoots": ["~/Documents", "~/Projects", "~/Work"],
                "diskPaths": ["~", "~/.cache", "~/.local/share", "~/.npm"]}
    return [Path(os.path.abspath(os.path.expanduser(path))) for path in options.get(key, defaults[key])]


def validate_options(options):
    if not isinstance(options, dict):
        raise ValueError("Options must be a JSON object.")
    for key in ("repositoryRoots", "diskPaths"):
        if key in options and (not isinstance(options[key], list) or len(options[key]) > 64 or
                               any(not isinstance(p, str) or not p or "\x00" in p for p in options[key])):
            raise ValueError(f"{key} must be an array of at most 64 nonempty paths.")
    depth = options.get("discoveryDepth", 3)
    if type(depth) is not int or not 0 <= depth <= 5:
        raise ValueError("discoveryDepth must be an integer from 0 to 5.")
    return options


def allocated_size(path, budget):
    """Measure independently per row; never sum overlapping or shared measurements."""
    total, count = 0, 0
    seen = set()
    stack = [Path(path)]
    local_deadline = min(budget.deadline, time.monotonic() + 1.5)
    problems = []
    root_device = None
    while stack:
        if (time.monotonic() >= local_deadline or count >= MAX_SCAN_ENTRIES or
                budget.entries >= MAX_TOTAL_ENTRIES):
            problems.append("scan limit reached")
            break
        current = stack.pop()
        try:
            info = current.lstat()
            if time.monotonic() >= local_deadline:
                problems.append("scan limit reached")
                break
            if root_device is None:
                root_device = info.st_dev
            if info.st_dev != root_device:
                problems.append("other filesystem skipped")
                continue
            identity = (info.st_dev, info.st_ino)
            if identity in seen:
                continue
            seen.add(identity)
            count += 1
            budget.entries += 1
            total += info.st_blocks * 512
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(current) as entries:
                    for entry in entries:
                        if time.monotonic() >= local_deadline or len(stack) + count >= MAX_SCAN_ENTRIES:
                            problems.append("scan limit reached")
                            break
                        # Queue paths only; lstat does not follow directory symlinks.
                        stack.append(Path(entry.path))
        except OSError:
            problems.append("inaccessible or disappeared entries")
    return {"bytes": str(total), "entries": str(count), "measurement": "partial" if problems else "complete"}, sorted(set(problems))


def measured_row(snapshot, path, budget):
    measurement, problems = allocated_size(path, budget)
    if problems:
        snapshot.note(f"Size for {path}: {', '.join(problems)}.", True)
    else:
        snapshot.successes += 1
    if int(measurement["entries"]):
        snapshot.successes += 1
    return {"path": str(path), **measurement}


def collect_disk(snapshot, options, budget):
    paths = configured_paths(options, "diskPaths")
    snapshot.note("Configured disk paths: " + (json.dumps([str(p) for p in paths], ensure_ascii=True) if paths else "none"))
    snapshot.note(SIZE_CAVEAT)
    columns = [("path", "Path"), ("bytes", "Allocated bytes"), ("entries", "Inodes counted"), ("measurement", "Measurement")]
    snapshot.table("paths", "Configured paths (independent measurements)", columns, [])
    rows = snapshot.data["tables"][-1]["rows"]
    snapshot.table("children", "Immediate children (independent measurements)", columns, [])
    children = snapshot.data["tables"][-1]["rows"]
    first_directory = None
    for path in paths:
        rows.append(measured_row(snapshot, path, budget))
        if first_directory is None and path.is_dir():
            first_directory = path
    if first_directory is not None:
        snapshot.note(f"Immediate children of {first_directory}; at most 100 children. Each size scan is limited to {MAX_SCAN_ENTRIES} entries and 1.5 seconds.")
        try:
            with os.scandir(first_directory) as entries:
                for entry in entries:
                    budget.check()
                    if len(children) == 100:
                        snapshot.note("Immediate children truncated to 100 rows.", True)
                        break
                    children.append(measured_row(snapshot, Path(entry.path), budget))
        except (OSError, CollectionError) as exc:
            snapshot.note(f"Immediate children unavailable/incomplete: {exc}", True)
    return snapshot.finish(f"{len(rows)} configured paths; {len(children)} children")


def git_args(path, *args):
    # Even read-only Git commands may invoke configured fsmonitor helpers or refresh the index.
    return ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
            "-C", str(path), *args]


def git_env():
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Invocation must inspect the selected repository, not an inherited override.
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(key, None)
    return env


def worktree_status(snapshot, path, budget):
    # Status can execute clean/process filters for same-size modified files. Read
    # configuration names only, never configured command strings or credentials.
    raw = command(snapshot, budget, git_args(path, "config", "--null", "--name-only", "--list"), env=git_env())
    if raw is None:
        return None
    filters = {key.rsplit(".", 1)[0] for key in raw.split("\x00")
               if key.startswith("filter.") and key.rsplit(".", 1)[-1] in ("clean", "process", "required")}
    if len(filters) > MAX_FILTERS or any("=" in key for key in filters):
        snapshot.note(f"Git status skipped for {path}: filter configuration cannot be safely bounded/overridden.", True)
        return None
    overrides = []
    for prefix in sorted(filters):
        for key, value in (("clean", ""), ("process", ""), ("required", "false")):
            overrides.extend(["-c", f"{prefix}.{key}={value}"])
    if filters:
        snapshot.note(f"Git content filters disabled for {path}; working-tree state compares unfiltered content and can differ from normal Git normalization.")
    return command(snapshot, budget, git_args(path, *overrides, "status", "--porcelain=v1", "-z", "--untracked-files=normal", "--ignore-submodules=all"), env=git_env())


def discover_repositories(snapshot, roots, depth, budget):
    visited, common_dirs, repositories = set(), set(), []
    stack = [(root, 0) for root in reversed(roots)]
    inspected = 0
    while stack:
        budget.check()
        path, level = stack.pop()
        if inspected >= MAX_DISCOVERY:
            snapshot.note(f"Repository discovery truncated after {MAX_DISCOVERY} directory entries.", True)
            break
        inspected += 1
        try:
            real = path.resolve(strict=True)
            if real in visited:
                continue
            visited.add(real)
            if not real.is_dir():
                snapshot.note(f"Repository root is not a directory: {path}", True)
                continue
            marker = real / ".git"
            if marker.is_dir() or marker.is_file() or ((real / "HEAD").is_file() and (real / "objects").is_dir()):
                raw = command(snapshot, budget, git_args(real, "rev-parse", "--git-common-dir"), env=git_env())
                if raw is not None:
                    # rev-parse emits a path followed by exactly one newline; retain embedded newlines.
                    common = Path(raw.removesuffix("\n"))
                    if not common.is_absolute():
                        common = real / common
                    common = common.resolve()
                    if common not in common_dirs:
                        common_dirs.add(common)
                        repositories.append(real)
                # Linked worktrees and repositories are discovery boundaries.
                continue
            if level >= depth:
                continue
            with os.scandir(real) as entries:
                for entry in entries:
                    budget.check()
                    inspected += 1
                    if inspected + len(stack) >= MAX_DISCOVERY:
                        snapshot.note(f"Repository discovery truncated at {MAX_DISCOVERY} queued/examined entries.", True)
                        break
                    if entry.name not in PRUNE and entry.is_dir(follow_symlinks=False):
                        stack.append((Path(entry.path), level + 1))
        except (OSError, RuntimeError):
            snapshot.note(f"Repository path inaccessible, missing or cyclic: {path}", True)
    return repositories


def parse_worktrees(raw):
    """-z keeps newlines, quotes, backslashes and Unicode paths unambiguous."""
    rows, current = [], {}
    for field in raw.split("\x00"):
        if not field:
            if current:
                if "path" not in current:
                    raise CollectionError("Git worktree record is missing its path.")
                rows.append(current)
                current = {}
            continue
        key, _, value = field.partition(" ")
        if not current and key != "worktree":
            raise CollectionError("Git worktree record is missing its path.")
        if key == "worktree":
            current["path"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key in ("detached", "bare"):
            current["branch"] = key
        elif key in ("locked", "prunable"):
            current[key] = value or "yes"
    if current:
        if "path" not in current:
            raise CollectionError("Git worktree record is missing its path.")
        rows.append(current)
    return rows


def parse_git_status(raw):
    fields = raw.split("\x00")
    count = 0
    index = 0
    while index < len(fields):
        item = fields[index]
        index += 1
        if not item:
            continue
        if len(item) < 4 or item[2] != " ":
            raise CollectionError("Git returned malformed porcelain status.")
        count += 1
        if "R" in item[:2] or "C" in item[:2]:
            if index >= len(fields) or not fields[index]:
                raise CollectionError("Git returned incomplete rename status.")
            index += 1
    return "clean" if count == 0 else f"{count} changed entries"


def collect_worktrees(snapshot, options, budget):
    roots = configured_paths(options, "repositoryRoots")
    depth = options.get("discoveryDepth", 3)
    snapshot.note("Repository roots: " + (json.dumps([str(p) for p in roots], ensure_ascii=True) if roots else "none"))
    snapshot.note(f"Discovery depth {depth}; at most {MAX_DISCOVERY} directory entries. Symlinked roots are resolved; descendant symlinks and dependency/cache/build directories are skipped. Repositories are discovery boundaries.")
    snapshot.note(SIZE_CAVEAT)
    snapshot.note(f"Size scans: at most {MAX_SCAN_ENTRIES} entries and 1.5 seconds each; {MAX_TOTAL_ENTRIES} entries across the snapshot. Git commands have a 3-second deadline.")
    rows, seen_paths = [], set()
    try:
        repositories = discover_repositories(snapshot, roots, depth, budget)
        for repo in repositories:
            raw = command(snapshot, budget, git_args(repo, "worktree", "list", "--porcelain", "-z"), env=git_env())
            if raw is None:
                continue
            try:
                trees = parse_worktrees(raw)
            except CollectionError as exc:
                snapshot.note(str(exc), True)
                continue
            for tree in trees:
                budget.check()
                path = Path(tree["path"])
                real = path.resolve()
                if real in seen_paths:
                    continue
                seen_paths.add(real)
                if len(rows) >= MAX_ROWS:
                    snapshot.note(f"Worktrees truncated to {MAX_ROWS} rows.", True)
                    break
                row = {"path": str(path), "branch": tree.get("branch", "unavailable"),
                       "locked": tree.get("locked", ""), "prunable": tree.get("prunable", ""),
                       "changes": "unavailable", "bytes": "unavailable", "measurement": "unavailable"}
                if tree.get("branch") == "bare":
                    row["changes"] = "bare repository"
                elif not path.is_dir():
                    row["changes"] = "missing or inaccessible"
                    snapshot.note(f"Worktree missing or inaccessible: {path}", True)
                else:
                    raw_status = worktree_status(snapshot, path, budget)
                    if raw_status is not None:
                        try:
                            row["changes"] = parse_git_status(raw_status)
                        except CollectionError as exc:
                            snapshot.note(str(exc), True)
                if path.is_dir():
                    row.update(measured_row(snapshot, path, budget))
                rows.append(row)
    except (CollectionError, OSError) as exc:
        snapshot.note(f"Worktree collection incomplete: {exc}", True)
    snapshot.note("Working-tree state counts porcelain entries; untracked directories count as one entry. Submodule contents are not inspected. No fetch, prune, checkout or index refresh is performed.")
    snapshot.table("worktrees", "Registered worktrees", [("path", "Path"), ("branch", "Branch / state"),
                   ("changes", "Working-tree state"), ("locked", "Locked"), ("prunable", "Prunable"),
                   ("bytes", "Allocated bytes"), ("measurement", "Measurement")], rows)
    return snapshot.finish(f"{len(rows)} worktrees")


def collect(section, options, budget=None):
    snapshot = Snapshot(section)
    snapshot.note(f"Snapshot limits: {COLLECTION_SECONDS} seconds, {MAX_OUTPUT} combined output bytes per command and {MAX_ROWS} rows per table. Limits produce explicit incomplete results.")
    try:
        return globals()["collect_" + section](snapshot, validate_options(options), budget or Budget())
    except Cancelled:
        snapshot.note("Collection cancelled.", True)
    except DeadlineReached:
        snapshot.note("Collection deadline reached; results are incomplete.", True)
    except (CollectionError, OSError, ValueError) as exc:
        snapshot.note(str(exc), True)
    return snapshot.finish("Collection incomplete")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("section", choices=SECTIONS)
    parser.add_argument("--options", default="{}", help="JSON settings object")
    args = parser.parse_args(argv)
    try:
        options = validate_options(json.loads(args.options))
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))
    def cancel(_signum, _frame):
        raise Cancelled()
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    def deadline(_signum, _frame):
        raise DeadlineReached()
    previous_alarm = signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, COLLECTION_SECONDS)
    try:
        result = collect(args.section, options)
    except DeadlineReached:
        snapshot = Snapshot(args.section)
        snapshot.note("Collection deadline reached; results are incomplete.", True)
        result = snapshot.finish("Collection incomplete")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_alarm)
    result["notes"].append("The deadline interrupts ordinary blocking calls; kernel uninterruptible I/O can delay process termination.")
    # ASCII escapes preserve every Linux filename byte represented via surrogateescape
    # while the JSON document remains valid UTF-8 for the QML consumer.
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
