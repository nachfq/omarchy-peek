# Using Peek

Click the Peek icon in the Omarchy bar. Opening a section collects one snapshot;
**Refresh** collects it again. The result displays its collection timestamp.
Switching sections cancels the current request. Closing the panel stops collection.
There is no refresh interval, scheduled scan, cleanup action or persistent history.

## Choose paths

Peek reads settings from its own entry in `~/.config/omarchy/shell.json`.
Preserve the surrounding configuration and edit the entry with `id: nachfq.peek`:

```json
{
  "id": "nachfq.peek",
  "repositoryRoots": ["~/src", "~/work"],
  "diskPaths": ["~/src", "~/.cache", "~/.local/share"],
  "discoveryDepth": 3
}
```

These are examples, not required directory names. Set `repositoryRoots` to
folders that contain your repositories, or to individual repositories. `~`
expands to your home directory; spaces are supported without shell escaping.
`discoveryDepth` limits repository discovery to 0–5 levels below the configured
roots. Dependency/cache/build directories are skipped. Git then supplies the
registered worktrees, including those located outside the discovery roots.

With no overrides, repository roots are `~/Documents`, `~/Projects` and `~/Work`;
disk paths are `~`, `~/.cache`, `~/.local/share` and `~/.npm`. Explicit empty
arrays select no paths. The Disk section shows configured totals and immediate
children of the first existing configured directory. These rows can overlap;
Peek does not claim their sum is a system-wide total.

Settings are read on a subsequent request. Omarchy reloads its shell configuration
when saved; open Peek and refresh the relevant section to collect new results.

## Read the result

- **OK:** the requested collection completed within its stated scope.
- **Partial:** some data was collected, with omitted or inaccessible portions
  explained in the notes.
- **Error:** the section could not produce its requested data. An unavailable
  Docker daemon, for example, is not reported as zero containers.

The timestamps describe when data was collected, not when a resource was created.
A service being enabled differs from it currently running. A stopped container
or old worktree remains a resource; Peek does not classify it as garbage.

## Troubleshooting

If a section reports a missing tool, check that its executable is available in
the Omarchy shell's PATH. Peek does not install dependencies or start services.
Docker access follows the current user's existing Docker configuration. Processes
and sockets owned by other users can have unavailable details.

Large roots may reach a collection deadline or discovery limit. Use narrower
configured roots and refresh to inspect a smaller scope. Git status includes
working-tree state; it is not a determination of whether deleting a worktree is
safe, and it does not fetch from remotes.

Disk measurements do not include every snapshot or filesystem reservation.
Filesystem free-space reporting and directory sizes answer different questions.
