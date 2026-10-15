#!/usr/bin/env python3
"""Isolated collector fixture. Records lifecycle, never queries the host."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('section')
parser.add_argument('--options', required=True, type=json.loads)
args = parser.parse_args()
log = Path(os.environ['PEEK_TEST_LOG'])

def record(event, **values):
    with log.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(event=event, pid=os.getpid(), section=args.section, **values)) + '\n')

record('start', options=args.options)
child = None
cancelled = False

def cancel(_signum, _frame):
    global cancelled
    if not cancelled:
        cancelled = True
        record('cancel')

signal.signal(signal.SIGTERM, cancel)
signal.signal(signal.SIGINT, cancel)
if args.section == 'disk':
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    record('child', child=child.pid)
    deadline = time.monotonic() + 3
    while not cancelled and time.monotonic() < deadline:
        time.sleep(.01)
else:
    time.sleep(.08)

if cancelled:
    if child:
        child.terminate()
        child.wait(timeout=2)
    # Simulate a backend completing during cancellation; the UI must ignore it.
    time.sleep(.12)
    record('cancelled')
else:
    if child:
        child.terminate()
        child.wait(timeout=2)
    record('finish')

if args.options.get('discoveryDepth') == 0:
    print('{malformed')
else:
    rows = [{'name': 'sample <b>literal</b>', 'path': '/fixture/a path with spaces/日本語/' + 'long-directory/' * 10, 'value': '42 MiB'}]
    if args.section == 'docker':
        rows += [{'name': 'entry ' + str(i), 'path': '/fixture/item/' + str(i), 'value': str(i)} for i in range(250)]
    if args.section == 'worktrees':
        rows = []
    status = {'services': 'partial', 'processes': 'error'}.get(args.section, 'ok')
    result = dict(schemaVersion=1, section=args.section, collectedAt='2026-01-01T12:00:00Z', status=status,
                  summary='Cancelled stale response' if cancelled else ('Access unavailable' if status == 'error' else 'Fixture snapshot'),
                  tables=[dict(id='fixture', title='Fixture table', columns=[dict(key='name', label='Name'), dict(key='path', label='Path'), dict(key='value', label='Size')], rows=rows)],
                  notes=['Fixture access limit. <b>plain text</b>'] if status != 'ok' else [])
    print(json.dumps(result))
