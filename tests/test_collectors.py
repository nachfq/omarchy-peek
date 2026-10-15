"""Portable collector tests. All mutable resources live in temporary directories."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "peek.py"
spec = importlib.util.spec_from_file_location("peek_collector", SCRIPT)
peek = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peek)


def table(result, ident):
    return next(item["rows"] for item in result["tables"] if item["id"] == ident)


def stopped(pid):
    try:
        # Orphaned zombies may await the host's reaper; they are already terminated.
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        return state == "Z"
    except FileNotFoundError:
        return True


class ProtocolTests(unittest.TestCase):
    def test_empty_configuration_is_successful_not_defaults(self):
        for section, key in (("disk", "diskPaths"), ("worktrees", "repositoryRoots")):
            result = peek.collect(section, {key: []})
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["schemaVersion"], 1)
            self.assertTrue(result["collectedAt"].endswith("Z"))
            self.assertTrue(all(not item["rows"] for item in result["tables"]))

    def test_options_validation(self):
        for value in ([], None, {"diskPaths": "~"}, {"diskPaths": [""]},
                      {"repositoryRoots": ["x\x00y"]}, {"discoveryDepth": True},
                      {"discoveryDepth": -1}, {"discoveryDepth": 6}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                peek.validate_options(value)
        with mock.patch.dict(os.environ, {"HOME": "/portable-home"}):
            self.assertEqual(peek.configured_paths({}, "repositoryRoots")[0], Path("/portable-home/Documents"))
            self.assertEqual(peek.configured_paths({"diskPaths": ["~/spaces ü"]}, "diskPaths"), [Path("/portable-home/spaces ü")])

    def test_cli_stdout_is_one_json_document(self):
        completed = subprocess.run([sys.executable, str(SCRIPT), "disk", "--options", '{"diskPaths":[]}'],
                                   capture_output=True, text=True, check=True)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(json.loads(completed.stdout)["section"], "disk")
        self.assertEqual(len(completed.stdout.splitlines()), 1)
        bad = subprocess.run([sys.executable, str(SCRIPT), "disk", "--options", "[]"], capture_output=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(bad.stdout, b"")

    def test_all_missing_tools_are_explicit_errors(self):
        with mock.patch.dict(os.environ, {"PATH": ""}):
            result = peek.collect("docker", {})
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("not installed" in note for note in result["notes"]))
        self.assertEqual(len(result["tables"]), 4)

    def test_generic_cells_are_strings_and_rows_bounded(self):
        snapshot = peek.Snapshot("disk")
        snapshot.table("a", "A", [("value", "Value")], [{"value": 123}] * (peek.MAX_ROWS + 1))
        result = snapshot.finish("test")
        self.assertEqual(len(table(result, "a")), peek.MAX_ROWS)
        self.assertTrue(all(row["value"] == "123" for row in table(result, "a")))
        self.assertNotEqual(result["status"], "ok")


class CommandTests(unittest.TestCase):
    def test_success_and_safe_error_without_stderr(self):
        self.assertEqual(peek.run_command([sys.executable, "-c", "print('ok')"], peek.Budget()), "ok\n")
        with self.assertRaises(peek.CollectionError) as caught:
            peek.run_command([sys.executable, "-c", "import sys; print('private-marker',file=sys.stderr);sys.exit(3)"], peek.Budget())
        self.assertNotIn("private-marker", str(caught.exception))

    def test_output_limit(self):
        with self.assertRaisesRegex(peek.CollectionError, "output exceeded"):
            peek.run_command([sys.executable, "-c", "print('x'*10000)"], peek.Budget(), max_output=100)

    def test_stderr_is_bounded_too(self):
        with self.assertRaisesRegex(peek.CollectionError, "output exceeded"):
            peek.run_command([sys.executable, "-c", "import sys;sys.stderr.write('x'*10000)"], peek.Budget(), max_output=100)

    def test_timeout_terminates_sigterm_ignoring_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "pid"
            child = "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"
            parent = ("import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c',sys.argv[2]]);"
                      "pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)")
            try:
                with self.assertRaisesRegex(peek.CollectionError, "timed out"):
                    peek.run_command([sys.executable, "-c", parent, str(pidfile), child], peek.Budget(), timeout=0.4)
                self.assertTrue(stopped(int(pidfile.read_text())))
            finally:
                if pidfile.exists() and not stopped(int(pidfile.read_text())):
                    os.kill(int(pidfile.read_text()), signal.SIGKILL)

    def test_descendant_pipe_survives_direct_child_exit(self):
        parent = "import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])"
        start = time.monotonic()
        with self.assertRaisesRegex(peek.CollectionError, "timed out"):
            peek.run_command([sys.executable, "-c", parent], peek.Budget(), timeout=0.25)
        self.assertLess(time.monotonic() - start, 2)

    def test_cli_alarm_interrupts_blocking_filesystem_call(self):
        # Exercise the real CLI signal deadline in a separate process, without
        # changing signal handlers in the unittest runner or blocking host I/O.
        code = ("import importlib.util,time;from pathlib import Path;from unittest import mock;"
                "s=importlib.util.spec_from_file_location('peek'," + repr(str(SCRIPT)) + ");"
                "p=importlib.util.module_from_spec(s);s.loader.exec_module(p);"
                "p.COLLECTION_SECONDS=.08;p.shutil.which=lambda command:None;original=Path.lstat;"
                "slow=lambda self:(time.sleep(2),original(self))[1];"
                "patch=mock.patch.object(Path,'lstat',slow);patch.start();"
                "p.main(['disk','--options','{\"diskPaths\":[\".\"]}'])")
        started = time.monotonic()
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=2, check=True)
        self.assertLess(time.monotonic() - started, 1.5)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "error")
        self.assertTrue(any("deadline" in note for note in response["notes"]))
        self.assertEqual(table(response, "paths"), [])

    def test_global_deadline_cannot_be_consumed_as_recoverable_tool_error(self):
        code = "\n".join([
            "import importlib.util,time,os",
            "from pathlib import Path",
            "s=importlib.util.spec_from_file_location('peek'," + repr(str(SCRIPT)) + ")",
            "p=importlib.util.module_from_spec(s);s.loader.exec_module(p)",
            "p.COLLECTION_SECONDS=.08",
            "phase={'status':False}",
            "p.discover_repositories=lambda *args:[Path('.') ]",
            "def is_dir(path):",
            "    if phase['status']: raise RuntimeError('continued filesystem access after deadline')",
            "    return True",
            "Path.is_dir=is_dir",
            "def run(args,budget,**kwargs):",
            "    if 'worktree' in args: return 'worktree '+os.getcwd()+'\\0branch refs/heads/fixture\\0\\0'",
            "    if 'config' in args: return ''",
            "    phase['status']=True",
            "    time.sleep(2)",
            "p.run_command=run",
            "p.main(['worktrees','--options','{\"repositoryRoots\":[\".\"]}'])",
        ])
        # Generated source needs NUL escapes, not literal backslash-zero fields.
        code = code.replace("\\0", "\\x00")
        started = time.monotonic()
        completed = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=2, check=True)
        self.assertLess(time.monotonic() - started, 1.5)
        response = json.loads(completed.stdout)
        self.assertNotEqual(response["status"], "ok")
        self.assertTrue(any("deadline" in note for note in response["notes"]))

    def test_cli_alarm_also_cleans_up_command_descendants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pidfile = root / "pid"
            fake = root / "docker"
            fake.write_text("#!" + sys.executable + "\n" +
                            "import subprocess,sys,time,pathlib\n" +
                            "p=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])\n" +
                            "pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(p.pid))\n" +
                            "time.sleep(60)\n")
            fake.chmod(0o700)
            code = ("import importlib.util; s=importlib.util.spec_from_file_location('peek'," + repr(str(SCRIPT)) + ");"
                    "p=importlib.util.module_from_spec(s);s.loader.exec_module(p);p.COLLECTION_SECONDS=.3;p.main(['docker'])")
            try:
                completed = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PATH=str(root)),
                                           capture_output=True, timeout=3, check=True)
                self.assertTrue(pidfile.exists())
                self.assertTrue(stopped(int(pidfile.read_text())))
                self.assertEqual(json.loads(completed.stdout)["status"], "error")
            finally:
                if pidfile.exists() and not stopped(int(pidfile.read_text())):
                    os.kill(int(pidfile.read_text()), signal.SIGKILL)

    def test_cli_sigterm_cancels_descendant_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pidfile = root / "pid"
            fake = root / "docker"
            fake.write_text("#!" + sys.executable + "\n" +
                            "import subprocess,sys,time,pathlib,signal\n" +
                            "p=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])\n" +
                            "pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(p.pid))\n" +
                            "time.sleep(60)\n")
            fake.chmod(0o700)
            env = dict(os.environ, PATH=str(root))
            process = subprocess.Popen([sys.executable, str(SCRIPT), "docker"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 3
                while not pidfile.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(pidfile.exists())
                process.terminate()
                stdout, stderr = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertTrue(stopped(int(pidfile.read_text())))
                self.assertIn("cancelled", " ".join(json.loads(stdout)["notes"]))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if pidfile.exists() and not stopped(int(pidfile.read_text())):
                    os.kill(int(pidfile.read_text()), signal.SIGKILL)


class ParserTests(unittest.TestCase):
    def test_docker_json_lines_and_json_array(self):
        self.assertEqual(peek.json_records('{"Name":"one"}\n{"Name":"two"}\n'), [{"Name": "one"}, {"Name": "two"}])
        self.assertEqual(peek.json_records('[{"unit":"sample.service"}]'), [{"unit": "sample.service"}])
        for raw in ("bad", "null", "[1]", '{"Name":'):
            with self.assertRaises(peek.CollectionError):
                peek.json_records(raw)

    def test_docker_includes_context_compose_and_disk_estimates(self):
        def fake(args, budget, **kwargs):
            if args[1:3] == ["context", "show"]:
                return "fixture-context\n"
            if args[1:3] == ["container", "ls"]:
                self.assertIn('com.docker.compose.project', args[-1])
                return '{"Names":"fixture","State":"running","composeProject":"sample"}\n'
            return ""
        with mock.patch.object(peek, "run_command", side_effect=fake):
            result = peek.collect("docker", {})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(table(result, "containers")[0]["composeProject"], "sample")
        self.assertTrue(any("fixture-context" in note for note in result["notes"]))
        self.assertTrue(any("not additive" in note for note in result["notes"]))

    def test_system_and_user_activation_enablement_and_timers(self):
        def fake(args, budget, **kwargs):
            if "list-units" in args:
                return '[{"unit":"sample.service","active":"active","sub":"running","description":"Sample"}]'
            if "list-unit-files" in args:
                return '[{"unit_file":"sample.service","state":"disabled"},{"unit_file":"idle.service","state":"enabled"}]'
            return '[{"unit":"sample.timer","activates":"sample.service","next":1000000,"last":0}]'
        with mock.patch.object(peek, "run_command", side_effect=fake):
            result = peek.collect("services", {})
        rows = table(result, "services")
        self.assertEqual({row["scope"] for row in rows}, {"system", "user"})
        self.assertEqual(next(row for row in rows if row["unit"] == "sample.service")["enablement"], "disabled")
        self.assertEqual(table(result, "timers")[0]["next"], "1970-01-01T00:00:01+00:00")
        self.assertEqual(table(result, "timers")[0]["last"], "n/a")

    def test_unavailable_activation_is_not_mislabeled_not_loaded(self):
        def fake(args, budget, **kwargs):
            if "list-units" in args:
                raise peek.CollectionError("manager unavailable")
            if "list-unit-files" in args:
                return '[{"unit_file":"sample.service","state":"enabled"}]'
            return '[]'
        with mock.patch.object(peek, "run_command", side_effect=fake):
            result = peek.collect("services", {})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(table(result, "services")[0]["active"], "unavailable")

    def test_proc_reads_only_name_status_and_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            process = root / "123"
            process.mkdir()
            (process / "comm").write_text("sample\n")
            (process / "status").write_text("Name:\tsample\nVmRSS:\t12 kB\n")
            (process / "cwd").symlink_to(root)
            with mock.patch.object(peek, "run_command", return_value="tcp LISTEN 0 128 [::]:1234 [::]:* users:((\"sample\",pid=123,fd=4))\n"):
                result = peek.collect_processes(peek.Snapshot("processes"), {}, peek.Budget(), root)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(table(result, "processes")[0]["rss"], str(12 * 1024))
            self.assertEqual(table(result, "sockets")[0]["local"], "[::]:1234")
            (process / "cwd").unlink()
            with mock.patch.object(peek, "run_command", side_effect=peek.CollectionError("ss missing")):
                result = peek.collect_processes(peek.Snapshot("processes"), {}, peek.Budget(), root)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(table(result, "processes")[0]["cwd"], "unavailable")
        self.assertEqual(peek.parse_rss("Name: kernel\n"), "unavailable")
        with self.assertRaises(ValueError):
            peek.parse_rss("VmRSS: 12 MB")
        with self.assertRaises(peek.CollectionError):
            peek.parse_sockets("malformed")

    def test_worktree_nul_protocol_preserves_unusual_names(self):
        raw = 'worktree /portable/space ü\n"quote\\name\x00HEAD abc\x00branch refs/heads/topic\x00locked reason\nline\x00\x00worktree /missing\x00detached\x00prunable missing\x00\x00'
        rows = peek.parse_worktrees(raw)
        self.assertEqual(rows[0]["path"], '/portable/space ü\n"quote\\name')
        self.assertEqual(rows[0]["locked"], "reason\nline")
        self.assertEqual(rows[1]["branch"], "detached")
        self.assertEqual(rows[1]["prunable"], "missing")
        with self.assertRaises(peek.CollectionError):
            peek.parse_worktrees("HEAD abc\x00\x00")

    def test_status_handles_rename_and_weird_names(self):
        self.assertEqual(peek.parse_git_status(""), "clean")
        self.assertEqual(peek.parse_git_status("R  new\nname\x00old\x00?? ü space\x00"), "2 changed entries")
        with self.assertRaises(peek.CollectionError):
            peek.parse_git_status("R  new\x00")


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        # Exercise Python fallback accounting independently of host du availability.
        patch = mock.patch.object(peek.shutil, "which", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def test_hardlinks_symlinks_and_overlap_are_not_invented_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "space ü"
            child.mkdir()
            data = child / "data"
            data.write_bytes(b"x" * 8192)
            os.link(data, child / "hardlink")
            (root / "cycle").symlink_to(root, target_is_directory=True)
            result = peek.collect("disk", {"diskPaths": [str(root), str(child)]})
            self.assertEqual(result["status"], "ok")
            rows = table(result, "paths")
            expected = root.lstat().st_blocks * 512 + child.lstat().st_blocks * 512 + data.lstat().st_blocks * 512 + (root / "cycle").lstat().st_blocks * 512
            self.assertEqual(int(rows[0]["bytes"]), expected)
            self.assertEqual(int(rows[1]["bytes"]), child.lstat().st_blocks * 512 + data.lstat().st_blocks * 512)
            self.assertNotIn("total", result)
            self.assertTrue(any("must not be added" in note for note in result["notes"]))

    def test_scan_bounds_and_missing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for n in range(5):
                (root / str(n)).write_text("data")
            with mock.patch.object(peek, "MAX_SCAN_ENTRIES", 2):
                row, problems = peek.allocated_size(root, peek.Budget())
            self.assertEqual(row["measurement"], "partial")
            self.assertLessEqual(int(row["entries"]), 2)
            self.assertIn("scan limit reached", problems)
            result = peek.collect("disk", {"diskPaths": [str(root / "missing")]})
            self.assertEqual(result["status"], "error")
            self.assertEqual(table(result, "paths")[0]["measurement"], "unavailable")

    def test_expired_measurement_is_never_labeled_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path.lstat
            def slow(path):
                time.sleep(.03)
                return original(path)
            with mock.patch.object(Path, "lstat", slow):
                result = peek.collect("disk", {"diskPaths": [tmp]}, peek.Budget(seconds=.01))
            self.assertNotEqual(result["status"], "ok")
            self.assertEqual(table(result, "paths")[0]["measurement"], "unavailable")

    def test_cyclic_repository_root_is_an_explicit_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").symlink_to(root / "b")
            (root / "b").symlink_to(root / "a")
            result = peek.collect("worktrees", {"repositoryRoots": [str(root / "a")]})
            self.assertEqual(result["status"], "error")

    def test_permission_error_does_not_become_successful_zero(self):
        with mock.patch.object(Path, "lstat", side_effect=PermissionError("denied")):
            result = peek.collect("disk", {"diskPaths": ["/fixture-denied"]})
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("inaccessible" in note for note in result["notes"]))

    def test_deadline_and_explicit_discovery_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one").mkdir()
            with mock.patch.object(peek, "MAX_DISCOVERY", 1):
                snapshot = peek.Snapshot("worktrees")
                self.assertEqual(peek.discover_repositories(snapshot, [root], 3, peek.Budget()), [])
                self.assertTrue(snapshot.failed)
            result = peek.collect("worktrees", {"repositoryRoots": [str(root)]}, peek.Budget(seconds=0))
            self.assertEqual(result["status"], "error")
            self.assertTrue(any("deadline" in note for note in result["notes"]))


@unittest.skipUnless(shutil.which("git"), "Git is unavailable")
class GitIntegrationTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                               "-c", "commit.gpgsign=false", "-C", str(root), *args],
                              check=True, capture_output=True).stdout

    def test_linked_worktrees_realpath_depth_state_and_no_git_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo space ü\nnewline"
            repo.mkdir()
            self.git(repo, "init")
            (repo / "tracked").write_text("base")
            self.git(repo, "add", "tracked")
            self.git(repo, "commit", "-m", "fixture")
            linked = root / "linked ü\nworktree"
            missing = root / "missing"
            self.git(repo, "worktree", "add", "-b", "linked", str(linked))
            self.git(repo, "worktree", "add", "-b", "missing", str(missing))
            self.git(repo, "worktree", "lock", "--reason", "fixture lock", str(linked))
            shutil.rmtree(missing)
            (linked / "tracked").write_text("changed")
            alias = root / "alias"
            alias.symlink_to(repo, target_is_directory=True)
            hook_marker = root / "fsmonitor-was-run"
            hook = root / "fsmonitor"
            hook.write_text("#!/bin/sh\nprintf ran > '" + str(hook_marker) + "'\n")
            hook.chmod(0o700)
            self.git(repo, "config", "core.fsmonitor", str(hook))
            gitdir = repo / ".git"
            before = {str(p.relative_to(gitdir)): (p.read_bytes(), p.stat().st_mtime_ns) for p in gitdir.rglob("*") if p.is_file()}
            result = peek.collect("worktrees", {"repositoryRoots": [str(alias), str(repo), str(linked)], "discoveryDepth": 0})
            self.assertEqual(result["status"], "partial", result["notes"])
            rows = table(result, "worktrees")
            self.assertEqual(len(rows), 3, rows)
            linked_row = next(row for row in rows if row["path"] == str(linked))
            self.assertEqual(linked_row["changes"], "1 changed entries")
            self.assertEqual(linked_row["locked"], "fixture lock")
            self.assertEqual(next(row for row in rows if row["path"] == str(missing))["changes"], "missing or inaccessible")
            after = {str(p.relative_to(gitdir)): (p.read_bytes(), p.stat().st_mtime_ns) for p in gitdir.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertFalse(hook_marker.exists())
            self.assertFalse(any(p.name.endswith(".lock") for p in gitdir.rglob("*")))
            # A root containing a repository requires depth one. Build/dependency trees are pruned.
            nested = root / "nested"
            nested.mkdir()
            self.git(nested, "init")
            ignored = root / "node_modules" / "ignored"
            ignored.mkdir(parents=True)
            self.git(ignored, "init")
            zero = peek.collect("worktrees", {"repositoryRoots": [str(root)], "discoveryDepth": 0})
            self.assertEqual(table(zero, "worktrees"), [])
            one = peek.collect("worktrees", {"repositoryRoots": [str(root)], "discoveryDepth": 1})
            self.assertFalse(any("ignored" in row["path"] for row in table(one, "worktrees")))
            self.assertTrue(any(row["path"] == str(nested) for row in table(one, "worktrees")))

    def test_status_never_runs_clean_or_process_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.git(root, "init")
            marker = root / "filter-ran"
            hook = root / "filter-hook"
            hook.write_text("#!/bin/sh\nprintf ran > '" + str(marker) + "'\ncat\n")
            hook.chmod(0o700)
            self.git(root, "config", "filter.fixture.clean", str(hook))
            (root / ".gitattributes").write_text("tracked filter=fixture\n")
            (root / "tracked").write_text("base")
            self.git(root, "add", "tracked", ".gitattributes")
            self.git(root, "commit", "-m", "fixture")
            self.assertTrue(marker.exists())
            marker.unlink()
            (root / "tracked").write_text("next")  # Same size forces Git to compare content.
            result = peek.collect("worktrees", {"repositoryRoots": [tmp], "discoveryDepth": 0})
            self.assertEqual(result["status"], "ok", result["notes"])
            self.assertFalse(marker.exists())
            self.assertTrue(any("unfiltered content" in note for note in result["notes"]))
            self.git(root, "config", "filter.fixture.process", str(hook))
            self.git(root, "config", "filter.fixture.required", "true")
            result = peek.collect("worktrees", {"repositoryRoots": [tmp], "discoveryDepth": 0})
            self.assertEqual(result["status"], "ok", result["notes"])
            self.assertFalse(marker.exists())

    def test_unbounded_or_unrepresentable_filters_skip_status(self):
        for key in ("filter.fixture.clean", "filter.a=b.clean"):
            snapshot = peek.Snapshot("worktrees")
            with mock.patch.object(peek, "run_command", return_value=key + "\x00") as run:
                with mock.patch.object(peek, "MAX_FILTERS", 0 if "fixture" in key else 64):
                    self.assertIsNone(peek.worktree_status(snapshot, Path("/fixture"), peek.Budget()))
            self.assertEqual(run.call_count, 1)
            self.assertTrue(snapshot.failed)

    def test_environment_repo_overrides_are_ignored(self):
        env = {"GIT_DIR": "/fixture-wrong", "GIT_WORK_TREE": "/fixture-wrong", "GIT_INDEX_FILE": "/fixture-wrong"}
        with mock.patch.dict(os.environ, env):
            effective = peek.git_env()
        self.assertNotIn("GIT_DIR", effective)
        self.assertNotIn("GIT_WORK_TREE", effective)
        self.assertNotIn("GIT_INDEX_FILE", effective)
        self.assertEqual(effective["GIT_OPTIONAL_LOCKS"], "0")


class CoverageTests(unittest.TestCase):
    def test_empty_and_failed_docker_tables_have_distinct_coverage(self):
        with mock.patch.object(peek, "run_command", return_value=""):
            result = peek.collect("docker", {})
        self.assertTrue(all(t["status"] == "ok" and not t["rows"] for t in result["tables"]))
        with mock.patch.object(peek, "run_command", side_effect=peek.CollectionError("unavailable")):
            result = peek.collect("docker", {})
        self.assertTrue(all(t["status"] == "error" for t in result["tables"]))
        def mixed(args, budget, **kwargs):
            if "volume" in args:
                return "malformed"
            return ""
        with mock.patch.object(peek, "run_command", side_effect=mixed):
            result = peek.collect("docker", {})
        self.assertEqual({t["id"]: t["status"] for t in result["tables"]},
                         {"containers": "ok", "images": "ok", "volumes": "error", "usage": "ok"})

    def test_service_and_timer_coverage_are_independent(self):
        def run(args, budget, **kwargs):
            if "list-timers" in args:
                raise peek.CollectionError("unavailable")
            return "[]"
        with mock.patch.object(peek, "run_command", side_effect=run):
            result = peek.collect("services", {})
        self.assertEqual({t["id"]: t["status"] for t in result["tables"]},
                         {"services": "ok", "timers": "error"})
        def one_scope(args, budget, **kwargs):
            if "--user" in args:
                raise peek.CollectionError("unavailable")
            return "[]"
        with mock.patch.object(peek, "run_command", side_effect=one_scope):
            result = peek.collect("services", {})
        self.assertTrue(all(t["status"] == "partial" for t in result["tables"]))

    def test_exhausted_size_budget_is_unavailable_and_note_is_grouped(self):
        budget = peek.Budget()
        budget.entries = peek.MAX_TOTAL_ENTRIES
        snapshot = peek.Snapshot("disk")
        with mock.patch.object(peek.shutil, "which", return_value=None):
            for path in (Path("one"), Path("two")):
                row = peek.measured_row(snapshot, path, budget)
                self.assertEqual(row["bytes"], "unavailable")
                self.assertEqual(row["entries"], "0")
                self.assertEqual(row["measurement"], "unavailable")
        self.assertEqual(len(snapshot.data["notes"]), 1)

    def test_worktree_deadline_preserves_completed_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / "first", root / "second"]
            for path in paths:
                path.mkdir()
            raw = "".join(f"worktree {path}\x00branch refs/heads/main\x00\x00" for path in paths)
            measurement = {"bytes": "4096", "entries": "1", "measurement": "complete"}
            with mock.patch.object(peek, "discover_repositories", return_value=[root]), \
                 mock.patch.object(peek, "run_command", return_value=raw), \
                 mock.patch.object(peek, "worktree_status", return_value=""), \
                 mock.patch.object(peek, "allocated_size", side_effect=[(measurement, []), peek.DeadlineReached()]):
                result = peek.collect("worktrees", {"repositoryRoots": [str(root)]})
            self.assertEqual(result["status"], "partial")
            self.assertEqual(len(table(result, "worktrees")), 1)
            self.assertEqual(table(result, "worktrees")[0]["bytes"], "4096")
            self.assertEqual(result["tables"][0]["status"], "partial")
            self.assertTrue(any("deadline" in note for note in result["notes"]))

    def test_native_size_zero_is_measured_without_inode_count(self):
        with mock.patch.object(peek.shutil, "which", return_value="/usr/bin/du"), \
             mock.patch.object(peek, "run_command", return_value="0\tfixture\x00") as run:
            row, problems = peek.allocated_size(Path("fixture"), peek.Budget())
        self.assertEqual(row, {"bytes": "0", "entries": "unavailable", "measurement": "complete"})
        self.assertEqual(problems, [])
        self.assertEqual(run.call_args.kwargs["timeout"], 1.5)
        self.assertEqual(run.call_args.args[0][-2:], ["--", "fixture"])

    def test_native_size_failure_and_malformed_output_fall_back(self):
        fallback = ({"bytes": "8", "entries": "1", "measurement": "partial"}, ["scan limit reached"])
        for output in ("12\twrong\x00", "12\tfixture", "-1\tfixture\x00", "12\tfixture\x00extra\x00",
                       peek.CollectionError("du timed out")):
            with self.subTest(output=output), \
                 mock.patch.object(peek.shutil, "which", return_value="/usr/bin/du"), \
                 mock.patch.object(peek, "run_command", side_effect=output if isinstance(output, Exception) else None,
                                   return_value=output), \
                 mock.patch.object(peek, "allocated_size_python", return_value=fallback) as native:
                self.assertEqual(peek.allocated_size(Path("fixture"), peek.Budget()), fallback)
                native.assert_called_once()

    def test_unmeasured_disk_tables_are_not_successful_empty_results(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(peek.shutil, "which", return_value=None):
            result = peek.collect("disk", {"diskPaths": [str(Path(tmp) / "missing")]})
        self.assertTrue(all(t["status"] == "error" for t in result["tables"]))
        self.assertEqual(table(result, "paths")[0]["bytes"], "unavailable")
        for section, key in (("disk", "diskPaths"), ("worktrees", "repositoryRoots")):
            result = peek.collect(section, {key: []})
            self.assertTrue(all(t["status"] == "ok" for t in result["tables"]))

    @unittest.skipUnless(shutil.which("du"), "native du is unavailable")
    def test_native_scan_preserves_hardlink_and_symlink_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "space ü\nname"
            root.mkdir()
            (root / "data").write_bytes(b"x" * 8192)
            os.link(root / "data", root / "hardlink")
            (root / "cycle").symlink_to(root, target_is_directory=True)
            native, problems = peek.allocated_size(root, peek.Budget())
            fallback, fallback_problems = peek.allocated_size_python(root, peek.Budget())
            self.assertEqual(problems, [])
            self.assertEqual(fallback_problems, [])
            self.assertEqual(native["measurement"], "complete")
            self.assertEqual(native["bytes"], fallback["bytes"])
            self.assertEqual(native["entries"], "unavailable")

    def test_native_global_deadline_does_not_start_fallback(self):
        with mock.patch.object(peek.shutil, "which", return_value="/usr/bin/du"), \
             mock.patch.object(peek, "run_command", side_effect=peek.DeadlineReached()), \
             mock.patch.object(peek, "allocated_size_python") as fallback:
            with self.assertRaises(peek.DeadlineReached):
                peek.allocated_size(Path("fixture"), peek.Budget())
            fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
