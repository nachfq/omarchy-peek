# Using Peek

Click the magnifying-glass icon in the Omarchy bar. **Overview** collects Docker,
services and worktrees in sequence and shows each result as it arrives. It does
not scan the Processes or Disk sections until you select them.

Choose a section to inspect its resource lists. **Refresh** collects the current
view again. Switching views cancels the active query; closing stops collection.
There is no refresh interval, scheduled scan, cleanup action or persistent history.

The main numbers are labeled observations, not a cleanup score. Docker categories
are separate disk estimates. Services distinguish user and system units;
“user service” does not imply that an agent created it. Worktree sizes are
independent measurements and are not added into a unique disk-usage total.

## Read the result

Filesystem and memory sizes use binary units (KiB, MiB, GiB); Docker keeps its
reported units. `≥` marks a partially scanned
lower bound; **Not measured** means no size observation was available, never zero.
An empty successful result differs from an unavailable query. A small status
indicator preserves incomplete/unavailable states without filling the view with
technical messages. Expand diagnostics for their causes and accounting notes.

Services initially focuses on running user services. Scope and state filters let
you inspect system units and inactive services too. Resource lists prioritize
measured consumption where sizes are available; full fields remain accessible in
the detailed view. Collection timestamps describe snapshot time, not creation time.

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

## Troubleshooting

After `omarchy plugin update nachfq.peek`, if the bar still opens the old
interface, run `omarchy restart shell` once to reload cached QML. The bar briefly
restarts; plugin settings and placement remain in the user configuration.

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
