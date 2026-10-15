# Omarchy Peek

Peek is an on-demand system inspection plugin for Omarchy 4 / Omarchy Shell.
The user opens it from the bar, reads facts, and optionally refreshes a section.
There is no periodic monitoring, inference, recommendation, cleanup or daemon.

## Agreed product

The MVP covers Docker resources and disk usage; system and user systemd services,
activation state and timers; processes and listening ports; Git worktrees with
paths, branches, size and working-tree state; and configurable disk paths.
Each result shows its collection time and explicit partial/unavailable states.
Closing the popup stops collection. UI and project documentation are English.

## Repository and reference

- Repository: https://github.com/nachfq/omarchy-peek (public, personal account).
- Plugin ID: `nachfq.peek`; initial release: `v0.1.0`; license: MIT.
- Reference: https://github.com/nachfq/omarchy-yuragi, also available as the sibling
  `../omarchy-yuragi`. Reuse its Omarchy-native bar/popup integration and isolated
  input-test patterns, not its audio subsystem or audio-specific restrictions.
- Installed Omarchy 4.0.4 is the local integration target. Its packaged files are
  read-only reference material. The public plugin publishing guide is
  https://plugins.omarchy.org/publish.html.
- QML hosts the popup in the existing shell. Short-lived Python standard-library
  collectors run only on user demand. Collection protocol is defined in
  `docs/collector-contract.md` before independent implementation begins.

## Execution

The user explicitly requested a versioned local agent context, execution plan,
parallel implementers where useful, and autonomous coordination through the MVP
GitHub release. This includes commits, pushes and necessary PR integration.
The coordinator maintains the plan and release evidence; implementers work in
separate branches/worktrees from a shared committed baseline.

Current plan: [MVP release](plans/mvp/plan.md).
