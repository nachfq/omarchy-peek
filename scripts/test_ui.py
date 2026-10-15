#!/usr/bin/env python3
"""Native input/lifecycle tests; --capture FILE also saves an offscreen preview.

Requires Quickshell, QtTest and an Omarchy shell (or OMARCHY_PATH). All settings,
process logs, native UI copies and fake collection live in a temporary directory.
No user's desktop configuration or real collectors are opened.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time


@contextmanager
def isolated_process(command, env):
    # A private process group bounds failure cleanup to resources this test
    # started, including helpers orphaned by a broken destruction path.
    process = subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        yield process
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        else:
            time.sleep(.2)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=2)
        process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, help='save a reproducible popup PNG')
    parser.add_argument('--capture-section', choices=['overview', 'docker', 'services', 'worktrees', 'processes', 'disk'], default='overview')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    shell = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy')) / 'shell'
    if not shutil.which('quickshell') or not (shell / 'Ui').is_dir():
        parser.error('Quickshell and Omarchy shell are required (set OMARCHY_PATH if needed)')
    with tempfile.TemporaryDirectory(prefix='peek-ui-') as directory:
        fixture = Path(directory)
        for name in ['Ui', 'Commons']:
            shutil.copytree(shell / name, fixture / name)
        # Redirect only home lookups in copied singleton configuration readers.
        # UI styling and controls otherwise use the installed public components.
        for name in ['Color.qml', 'Style.qml']:
            path = fixture / 'Commons' / name
            path.write_text(path.read_text().replace('Quickshell.env("HOME")', 'Quickshell.env("PEEK_TEST_HOME")'))
        for path in list(root.glob('*.qml')) + [root / 'Model.js']:
            shutil.copy2(path, fixture / path.name)
        shutil.copy2(root / 'tests/ui/KeyboardPanel.qml', fixture / 'Ui/KeyboardPanel.qml')
        shutil.copy2(root / 'tests/ui/shell.qml', fixture / 'shell.qml')
        (fixture / 'scripts').mkdir()
        shutil.copy2(root / 'tests/ui/fake_collector.py', fixture / 'scripts/peek.py')
        log = fixture / 'events.jsonl'
        # Separate XDG roots prevent singleton theme/config readers in the
        # unchanged native UI from reading or writing the user's desktop files.
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='',
                   QT_QUICK_BACKEND='software', PEEK_TEST_LOG=str(log),
                   PEEK_TEST_HOME=str(fixture / 'home'), PEEK_PREVIEW_SECTION=args.capture_section,
                   XDG_CONFIG_HOME=str(fixture / 'config'), XDG_CACHE_HOME=str(fixture / 'cache'),
                   XDG_DATA_HOME=str(fixture / 'data'), XDG_RUNTIME_DIR=str(fixture / 'runtime'))
        Path(env['XDG_RUNTIME_DIR']).mkdir(mode=0o700)
        env.pop('WAYLAND_DISPLAY', None)
        env.pop('DISPLAY', None)
        env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        env.pop('SWAYSOCK', None)
        env.pop('I3SOCK', None)
        env.pop('PEEK_PREVIEW_PATH', None)
        if args.capture:
            args.capture = args.capture.resolve()
            args.capture.parent.mkdir(parents=True, exist_ok=True)
            env['PEEK_PREVIEW_PATH'] = str(args.capture)
        with isolated_process(['quickshell', '-p', str(fixture / 'shell.qml'), '--no-color'], env) as process:
            try:
                output, _ = process.communicate(timeout=55)
            except subprocess.TimeoutExpired as error:
                print((error.stdout or b'').decode(errors='replace'))
                raise
            print(output)
            summaries = [line.split('PEEK_UI_RESULT ', 1)[1] for line in output.splitlines() if 'PEEK_UI_RESULT ' in line]
            assert process.returncode == 0 and len(summaries) == 1, 'UI fixture did not finish'
            counts = json.loads(summaries[0])
            assert counts['failed'] == 0 and counts['passed'] >= 12, counts
            events = [json.loads(line) for line in log.read_text().splitlines()]
            active = set()
            children = []
            for event in events:
                if event['event'] == 'start':
                    # Tests also create/destroy one separate panel, sequentially.
                    assert not active, ('Overlapping collectors', event, sorted(active))
                    active.add(event['pid'])
                elif event['event'] in ('finish', 'cancelled'):
                    active.remove(event['pid'])
                elif event['event'] == 'child':
                    children.append(event['child'])
            assert not active, ('Collector left running', active)
            assert any(event['event'] == 'cancelled' for event in events), 'Cancellation was not exercised'
            assert any(event.get('options') == {'repositoryRoots': ['/fixture/space and 日本語'], 'diskPaths': [], 'discoveryDepth': 2} for event in events), 'Inline options did not reach argv intact'
            for pid in children:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    continue
                raise AssertionError(f'Fixture child still running: {pid}')
            if args.capture:
                assert args.capture.is_file() and args.capture.stat().st_size > 1000, 'Preview not captured'
            print(f"Lifecycle verified: {sum(e['event'] == 'start' for e in events)} requests; no overlap or surviving fixture children")


if __name__ == '__main__':
    main()
