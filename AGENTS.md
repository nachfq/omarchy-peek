# Working on Peek

Read `.agent-context/context.md` and the active plan before implementation.
Keep instructions, code, UI text, and documentation in English.

- Peek is a read-only, on-demand Omarchy Shell plugin. Only opening a section or
  pressing Refresh may start collection. Closing the panel cancels its collectors.
- No background polling, automatic cleanup, recommendations, agent attribution,
  network telemetry, privilege escalation, package installs, or host mutation.
- Reuse Omarchy's public QML UI and plugin contract. Never edit packaged Omarchy
  files or change the user's desktop configuration during automated tests.
- Keep collection out of the QML event loop. Use Python's standard library and
  bounded subprocesses; pass argument arrays, never concatenate shell commands.
- Do not inspect secrets, process environments, or full command lines. Show
  process names, PID, memory, current directory and listening sockets as available.
- Keep machine-specific paths, diagnostics, session IDs and runtime snapshots out
  of Git. Configurable paths belong in the user's plugin settings.
- Tests must exercise parsing, failure states, cancellation and actual UI input.
  Record only checks actually run. Use isolated fixtures for desktop integration.
- The coordinator owns shared context, contracts, CI, integration and publication.
  Independent implementers own only their assigned paths and branches.
- The user authorized autonomous work through the MVP GitHub release, including
  necessary commits, pushes, PRs and integration. Do not create extra checkpoints
  for already-authorized work. No marketplace submission is in this scope.
