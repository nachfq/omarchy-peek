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
    def table(ident, title, columns, rows, status='ok'):
        return dict(id=ident, title=title, columns=[dict(key=k, label=v) for k, v in columns], rows=rows, status=status)

    if args.section == 'docker':
        tables = [table('containers', 'Containers', [(k, k) for k in ['Names', 'State', 'Status', 'Ports', 'composeProject']],
            [dict(Names='sample <b>literal</b>', State='running', Status='Up 2 hours', Ports='127.0.0.1:5432', composeProject='日本語')] +
            [dict(Names='project-' + str(i), State='running' if i < 3 else 'exited', Status='Up 3 hours' if i < 3 else 'Exited', Ports='', composeProject='demo') for i in range(40)]),
            table('usage', 'Docker disk usage', [(k,k) for k in ['Type', 'TotalCount', 'Active', 'Size', 'Reclaimable']],
            [dict(Type=t, TotalCount=n, Active='2', Size=size, Reclaimable='0B') for t,n,size in [('Images','18','9.325GB'),('Local Volumes','6','82.87MB'),('Build Cache','24','328.2MB'),('Containers','41','14.3MB')]]),
            table('images', 'Images', [(k,k) for k in ['Repository','Tag','ID','Size']], [dict(Repository='postgres',Tag='16',ID='abc123',Size='430MB')]),
            table('volumes', 'Volumes', [(k,k) for k in ['Name','Driver','Scope']], [dict(Name='project-data',Driver='local',Scope='local')])]
    elif args.section == 'services':
        tables = [table('services', 'Services', [(k,k) for k in ['scope','unit','active','sub','enablement','description']],
            [dict(scope=scope, unit=unit, active=active, sub=sub, enablement='enabled', description=desc) for scope,unit,active,sub,desc in [
                ('user','pipewire.service','active','running','Audio service'),('user','syncthing.service','active','running','File synchronization'),
                ('user','backup.service','inactive','dead','Scheduled backup'),('system','NetworkManager.service','active','running','Network manager'),
                ('system','demo.service','not loaded','','Demo service')]]),
            table('timers','Timers',[(k,k) for k in ['scope','unit','activates','next','last']],[], 'error')]
    elif args.section == 'worktrees':
        tables = [table('worktrees','Registered worktrees',[(k,k) for k in ['path','branch','changes','bytes','measurement','entries']],
            [dict(path='/projects/' + name, branch=branch, changes='clean', bytes=size, measurement=measurement, entries='unavailable') for name,branch,size,measurement in [
                ('peek','main','32505856','complete'),('workspace','feature/dashboard','4294967296','partial'),
                ('studio','main','1288490188','complete'),('archived','release','unavailable','unavailable')]], 'partial')]
    elif args.section == 'disk':
        tables = [table('paths','Configured paths',[(k,k) for k in ['path','bytes','entries','measurement']],[])]
    else:
        tables = [table('processes','Processes',[(k,k) for k in ['pid','name','rss','cwd']],[], 'error')]
    status = {'services':'partial','processes':'error','worktrees':'partial'}.get(args.section,'ok')
    result = dict(schemaVersion=1, section=args.section, collectedAt='2026-01-01T12:00:00Z', status=status,
                  summary='Cancelled stale response' if cancelled else {'docker':'41 containers','services':'5 services; timers unavailable','processes':'Access unavailable','worktrees':'4 registered worktrees','disk':'No configured paths'}[args.section],
                  tables=tables, notes=['Fixture accounting note. <b>plain text</b>', 'Measurements are independent; partial sizes are lower bounds.'])
    print(json.dumps(result))
