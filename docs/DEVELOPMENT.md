# Development

Read [AGENTS.md](../AGENTS.md), the [project context](../.agent-context/context.md)
and [MVP plan](../.agent-context/plans/mvp/plan.md). The
[collector protocol](collector-contract.md) is the shared Python/QML boundary.

## Local checks

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
omarchy plugin validate .
scripts/check_qml.sh
python3 scripts/test_ui.py
QT_SCALE_FACTOR=1.5 python3 scripts/test_ui.py
```

Collector tests use temporary directories and synthetic command output. UI tests
use an isolated Quickshell fixture with fake collector data and the installed
Omarchy UI components. They must exercise actual pointer/keyboard input and
request lifecycle, including closing while collection is active. They do not
modify the user's installed shell configuration.

QML checks require Omarchy Shell and Qt/Quickshell. Set `OMARCHY_PATH` to a separate
Omarchy checkout when testing against a reference version. CI pins the Omarchy
4.0.4 source contract and uses an Arch environment for the Qt/Quickshell tools.

## Read-only manual collection

```sh
python3 scripts/peek.py docker --options '{}'
python3 scripts/peek.py services --options '{}'
python3 scripts/peek.py processes --options '{}'
python3 scripts/peek.py worktrees --options '{"repositoryRoots":["."],"discoveryDepth":0}'
python3 scripts/peek.py disk --options '{"diskPaths":["."]}'
```

These commands emit local system details. Keep output out of Git and public
issues unless reviewed and redacted. The fixture data in tests is synthetic.

## Release

1. Verify the integrated diff, portable tests, QML checks and native input tests.
2. Compare real collector results with the underlying tools and inspect the popup.
3. Complete the independent delivery review and address concrete findings.
4. Merge the reviewed integration PR after CI passes.
5. Verify the public default-branch contents and manifest version.
6. Tag that exact commit as `v0.1.0` and publish the GitHub release notes.

The GitHub source archives are the release artifacts; no binary compilation or
package registry is needed. Marketplace submission is a separate action.
