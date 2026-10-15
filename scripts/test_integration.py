#!/usr/bin/env python3
"""Exercise the actual UI/collector protocol and cancellation in an isolated fixture.

Default: offscreen, read-only collection using this account's existing tools.
--wayland: briefly open a native popup on the active compositor and verify focus,
placement and Escape. Neither mode changes the user's shell configuration.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time


def run(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wayland', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    shell = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy')) / 'shell'
    if args.wayland and not os.environ.get('WAYLAND_DISPLAY'):
        parser.error('--wayland requires an active Wayland compositor')
    if not (root / 'scripts/peek.py').is_file():
        parser.error('integrated collector scripts/peek.py is required')
    with tempfile.TemporaryDirectory(prefix='peek-integration-') as directory:
        fixture = Path(directory)
        for name in ['Ui', 'Commons']:
            shutil.copytree(shell / name, fixture / name)
        for name in ['Color.qml', 'Style.qml']:
            path = fixture / 'Commons' / name
            path.write_text(path.read_text().replace('Quickshell.env("HOME")', 'Quickshell.env("PEEK_TEST_HOME")'))
        for path in list(root.glob('*.qml')) + [root / 'Model.js']:
            shutil.copy2(path, fixture / path.name)
        if not args.wayland:
            shutil.copy2(root / 'tests/ui/KeyboardPanel.qml', fixture / 'Ui/KeyboardPanel.qml')
        qml = (root / 'tests/integration/shell.qml').read_text()
        if not args.wayland:
            qml = qml.replace('PanelWindow {', 'FloatingWindow {')
            qml = qml.replace('anchors { top: true; left: true; right: true }', 'implicitWidth: 160')
            qml = qml.replace('exclusionMode: ExclusionMode.Ignore', '')
        (fixture / 'shell.qml').write_text(qml)
        (fixture / 'scripts').mkdir()
        shutil.copy2(root / 'scripts/peek.py', fixture / 'scripts/peek.py')
        if (root / 'peek').is_dir():
            shutil.copytree(root / 'peek', fixture / 'peek')
        repository = fixture / 'sample repository'
        run(['git', 'init', '--initial-branch=main', str(repository)])
        (repository / 'README.txt').write_text('Synthetic integration fixture.\n')
        run(['git', '-C', str(repository), 'add', 'README.txt'])
        run(['git', '-C', str(repository), '-c', 'commit.gpgsign=false', '-c',
             'core.hooksPath=/dev/null', '-c', 'user.name=Peek Test', '-c',
             'user.email=peek@example.invalid', 'commit', '-m', 'test fixture'])
        options = {'repositoryRoots': [str(repository)], 'diskPaths': [str(repository)], 'discoveryDepth': 0}
        env = dict(os.environ, QT_QPA_PLATFORMTHEME='', QT_QUICK_BACKEND='software',
                   PEEK_TEST_OPTIONS=json.dumps(options), PEEK_TEST_HOME=str(fixture / 'home'),
                   PEEK_TEST_WAYLAND='1' if args.wayland else '0',
                   XDG_CONFIG_HOME=str(fixture / 'config'), XDG_CACHE_HOME=str(fixture / 'cache'),
                   XDG_DATA_HOME=str(fixture / 'data'))
        if args.wayland:
            env['QT_QPA_PLATFORM'] = 'wayland'
        else:
            env['QT_QPA_PLATFORM'] = 'offscreen'
            env['XDG_RUNTIME_DIR'] = str(fixture / 'runtime')
            Path(env['XDG_RUNTIME_DIR']).mkdir(mode=0o700)
            for key in ['WAYLAND_DISPLAY', 'DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE', 'SWAYSOCK', 'I3SOCK']:
                env.pop(key, None)
        fake_bin = fixture / 'bin'
        fake_bin.mkdir()
        pid_file = fixture / 'docker-pid'
        pid_file.write_text('')
        docker = fake_bin / 'docker'
        docker.write_text('#!/usr/bin/env python3\nimport os,time\nfrom pathlib import Path\n'
                          'Path(os.environ["PEEK_CHILD_PID"]).write_text(str(os.getpid()))\n'
                          'time.sleep(60)\n')
        docker.chmod(0o755)
        for mode in ['real', 'cancel']:
            child_env = dict(env, PEEK_TEST_MODE=mode, PEEK_CHILD_PID=str(pid_file))
            if mode == 'cancel':
                child_env.update(PATH=str(fake_bin) + os.pathsep + env['PATH'], PEEK_CHILD_PID=str(pid_file))
            process = subprocess.Popen(['quickshell', '-p', str(fixture / 'shell.qml'), '--no-color'],
                                       env=child_env, text=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                output, _ = process.communicate(timeout=180)
                print(output)
                summaries = [line.split('PEEK_INTEGRATION_RESULT ', 1)[1] for line in output.splitlines()
                             if 'PEEK_INTEGRATION_RESULT ' in line]
                assert process.returncode == 0 and len(summaries) == 1, 'Integration fixture did not finish'
                counts = json.loads(summaries[0])
                assert counts['failed'] == 0 and counts['passed'] >= 1, counts
                if mode == 'real':
                    assert output.count('PEEK_REAL_SECTION ') == 5, 'Not all real sections were checked'
                else:
                    assert pid_file.is_file(), 'Real collector never started the blocking command'
                    pid = int(pid_file.read_text())
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        pass
                    else:
                        raise AssertionError('Cancelled real collector left its command running')
                print('Integrated runtime verified:', mode, 'native Wayland' if args.wayland else 'offscreen')
            finally:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    time.sleep(.2)
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=3)
                process.stdout.close()
                # A broken helper may create a separate child process group.
                # Clean up only the exact synthetic command started by this test.
                if mode == 'cancel' and pid_file.is_file() and pid_file.read_text().strip():
                    pid = int(pid_file.read_text())
                    try:
                        cmdline = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
                        if str(docker).encode() in cmdline:
                            os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except FileNotFoundError:
                        pass


if __name__ == '__main__':
    main()
