---
{"id":"mvp","title":"Release Peek 0.1.0 for on-demand system inspection","status":"active","depends_on":[]}
---

# Release Peek 0.1.0

## Specs

- **S1 On demand:** Open a bar popup; selecting a section or pressing Refresh runs
  one snapshot. Closing cancels the complete collector process tree. No polling.
- **S2 Facts:** Docker, system/user services and timers, processes/ports,
  worktrees and disk sections display observed values and collection timestamps.
  No inference, recommendations, cleanup controls or historical agent attribution.
- **S3 Honest limits:** Partial failures, missing tools/access, bounded discovery,
  truncated output and filesystem accounting limitations are visible. Empty is
  distinguishable from unavailable. Paths are configurable through inline settings.
- **S4 Native UI:** Follow Omarchy's theme, popup and keyboard conventions, with
  readable scrollable results, loading/error states and manual refresh. Reuse
  verified Yuragi patterns. UI text is English.
- **S5 Lightweight:** Python standard library plus existing system tools. Helpers
  run only on demand; no persistent data service or privileged operations.
- **S6 Reproducible release:** MIT license, install/config/use documentation,
  meaningful tests, passing CI, independently reviewed integration, tagged GitHub
  release `v0.1.0` from the validated default branch.
- **S7 Versioned context:** Store durable context and execution plan in this repo.
  Keep personal paths, runtime data and orchestration session state out of Git.

Scope is user-agreed for autonomous execution through GitHub publication.
Marketplace submission and automatic/user-triggered cleanup are excluded.

## Technical approach

Peek's QML bar button opens a native popup with five sections. Selecting Docker,
for example, starts a short-lived Python process which queries the existing
Docker context and returns a structured snapshot. The popup renders generic
string tables and the result timestamp. Refresh replaces that snapshot; closing
terminates the request. Slow disk scans cannot block the UI or other sections.

The collector and UI communicate through [collector protocol v1](../../../docs/collector-contract.md).
This stable boundary enables two independent implementers: one owns Python
collection/tests, one owns QML/UI tests. The coordinator owns contracts, context,
documentation, CI and release integration. Both start from the same committed
bootstrap and target the `feature/mvp` integration branch.

Portable defaults inspect conventional user directories. Inline plugin settings
select repository roots and disk paths. Repository discovery is bounded and
reports its boundaries. Disk measurements are allocated-byte estimates, not
estimates of space that deletion would recover.

Yuragi provides the native bar/panel, theme and isolated Qt input-test patterns.
Its audio service is unrelated to this plugin. All host configuration remains
untouched by automated tests; isolated runtime/config locations cover integration.

## Tasks

### D1 Shared foundation
- **T1** (S7, S4), done, owner coordinator: verify shell/reference contracts,
  write context/plan/protocol, initialize a shared Git baseline. Verify plan
  reader, ignore policy, clean baseline and branch identities. Evidence: reader
  discovered `mvp`; context is trackable; baseline `94266cc` is committed and both
  implementers branched from it. The public default branch is `main`.

### D2 Parallel implementation
- **T2** (S1–S3, S5), active, depends T1, owner collector implementer:
  implement `scripts/peek.py`, `peek/` package if needed and
  `tests/test_collectors.py`/collector fixtures. Verify portable unit tests,
  failure/cancellation behavior and real read-only smoke collection.
- **T3** (S1, S3–S5), active, depends T1, owner UI implementer: implement root QML,
  `Model.js` if needed, `manifest.json`, `tests/ui/`, `tests/*qml*`,
  `scripts/check_qml.sh`, `scripts/test_ui.py`. Verify manifest, lint and native
  input/lifecycle tests at scales 1 and 1.5 using a fake collector.
- **T4** (S6), active, depends T1, owner coordinator: README/license, usage and
  development docs, portable and QML CI, release validation scripts as needed.

### D3 Integrate and publish
- **T5** (S1–S6), pending, depends T2–T4, owner coordinator: inspect worker diffs,
  integrate reviewed commits, verify all collectors and real popup lifecycle,
  visually inspect a rendered popup, run independent cumulative review and fix
  concrete issues. Record actual evidence and limits.
- **T6** (S6–S7), pending, depends T5, owner coordinator: finish plan evidence,
  publish integration PR, verify CI, merge under user's release authorization,
  validate default-branch install content and publish `v0.1.0` release.

## Next delivery

Autonomous scope: D1–D3, explicitly requested by the user. No intermediate human
checkpoint is required for this agreed MVP; unresolved consequential product
changes must still be surfaced. Current checkpoint: T2 and T3 are running in independent
implementer worktrees; the coordinator is preparing T4 documentation and CI.
Application validation awaits implementation; foundation checks passed.
